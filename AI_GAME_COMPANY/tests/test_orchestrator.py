"""Unit tests for the orchestrator core.

    python3 -m unittest discover -s tests -v

Every test writes into a temporary directory, so running them never touches
the live company state, queue or license registry.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.orchestrator import artifact_validator, logging_setup, retry_manager
from company.orchestrator.license_manager import (APPROVED, UNKNOWN, LicenseEntry,
                                                  LicenseManager)
from company.orchestrator.policy import PaidActionBlocked, Policy
from company.orchestrator.state_manager import StateManager
from company.orchestrator.task_queue import Task, TaskQueue


class TempCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


class TestPolicy(TempCase):
    def _policy(self, **overrides) -> Policy:
        data = {"allow_paid_api": False, "allow_auto_purchase": False,
                "ollama_local_only": True, "allow_ollama_cloud": False,
                "blocked_env_keys": ["OPENAI_API_KEY", "FAL_KEY"]}
        data.update(overrides)
        path = self.tmp / "policy.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return Policy.load(path)

    def test_defaults_are_safe_when_file_missing(self):
        policy = Policy.load(self.tmp / "nope.json")
        self.assertFalse(policy.get("allow_paid_api"))
        self.assertFalse(policy.get("allow_auto_purchase"))
        self.assertIsNone(policy.source)

    def test_paid_guard_raises(self):
        with self.assertRaises(PaidActionBlocked):
            self._policy().guard_paid_api("test")

    def test_paid_guard_allows_when_enabled(self):
        self._policy(allow_paid_api=True).guard_paid_api("test")  # must not raise

    def test_blocked_keys_stripped_from_child_env(self):
        env = {"PATH": "/usr/bin", "OPENAI_API_KEY": "sk-x", "FAL_KEY": "f",
               "KEEP_ME": "1"}
        sanitized = self._policy().sanitized_env(env=env)
        self.assertNotIn("OPENAI_API_KEY", sanitized)
        self.assertNotIn("FAL_KEY", sanitized)
        self.assertEqual(sanitized["KEEP_ME"], "1")

    def test_keys_kept_when_paid_api_allowed(self):
        env = {"OPENAI_API_KEY": "sk-x"}
        sanitized = self._policy(allow_paid_api=True).sanitized_env(env=env)
        self.assertIn("OPENAI_API_KEY", sanitized)

    def test_remote_ollama_endpoint_blocked(self):
        policy = self._policy(ollama_endpoint="https://ollama.example.com")
        with self.assertRaises(PaidActionBlocked):
            policy.ollama_endpoint()

    def test_localhost_ollama_endpoint_allowed(self):
        policy = self._policy(ollama_endpoint="http://localhost:11434/")
        self.assertEqual(policy.ollama_endpoint(), "http://localhost:11434")


class TestStateManager(TempCase):
    def test_init_update_reload(self):
        sm = StateManager(self.tmp / "state.json")
        sm.init()
        sm.update(current_game="Game01", current_phase="SCENARIO")
        reloaded = StateManager(self.tmp / "state.json").load()
        self.assertEqual(reloaded["current_game"], "Game01")
        self.assertEqual(reloaded["current_phase"], "SCENARIO")

    def test_corrupt_state_is_quarantined_not_fatal(self):
        path = self.tmp / "state.json"
        path.write_text("{not json", encoding="utf-8")
        state = StateManager(path).load()
        self.assertEqual(state["current_phase"], "INFRASTRUCTURE")
        self.assertTrue((self.tmp / "state.corrupt.json").exists())

    def test_missing_apk_revokes_success(self):
        sm = StateManager(self.tmp / "state.json")
        sm.init()
        sm.update(build_status="SUCCESS")
        sm.register_artifact("apk", self.tmp / "nope.apk")
        report = sm.verify_against_disk()
        self.assertFalse(report["consistent"])
        self.assertEqual(sm.load()["build_status"], "REVOKED_ARTIFACT_MISSING")

    def test_present_apk_keeps_success(self):
        sm = StateManager(self.tmp / "state.json")
        sm.init()
        apk = self.tmp / "real.apk"
        apk.write_bytes(b"PK\x03\x04payload")
        sm.update(build_status="SUCCESS")
        sm.register_artifact("apk", apk)
        self.assertTrue(sm.verify_against_disk()["consistent"])
        self.assertEqual(sm.load()["build_status"], "SUCCESS")


class TestTaskQueue(TempCase):
    def _queue(self) -> TaskQueue:
        return TaskQueue(self.tmp / "tasks.sqlite3")

    def test_priority_order(self):
        q = self._queue()
        q.enqueue(Task(task_id="low", goal="low", priority=200))
        q.enqueue(Task(task_id="high", goal="high", priority=1))
        self.assertEqual(q.claim_next().task_id, "high")

    def test_pass_requires_evidence(self):
        q = self._queue()
        q.enqueue(Task(task_id="t", goal="g"))
        q.claim_next()
        with self.assertRaises(ValueError):
            q.mark_pass("t", {})
        with self.assertRaises(ValueError):
            q.mark_pass("t", {"note": "the agent said it is done"})
        q.mark_pass("t", {"acceptance_checked": True, "checks": ["file exists"]})
        self.assertEqual(q.get("t").status, "PASS")

    def test_invalid_status_rejected(self):
        q = self._queue()
        q.enqueue(Task(task_id="t", goal="g"))
        with self.assertRaises(ValueError):
            q.set_status("t", "DEFINITELY_DONE")

    def test_resume_finds_interrupted_task(self):
        q = self._queue()
        q.enqueue(Task(task_id="t", goal="g"))
        q.claim_next()
        fresh = TaskQueue(self.tmp / "tasks.sqlite3")
        self.assertIn("t", [t.task_id for t in fresh.resume_candidates()])

    def test_history_records_transitions(self):
        q = self._queue()
        q.enqueue(Task(task_id="t", goal="g"))
        q.claim_next()
        q.set_status("t", "FAILED", note="boom")
        transitions = [(h["from_status"], h["to_status"]) for h in q.history("t")]
        self.assertIn(("QUEUED", "RUNNING"), transitions)
        self.assertIn(("RUNNING", "FAILED"), transitions)


class TestRetryManager(TempCase):
    def _rm(self, **overrides) -> retry_manager.RetryManager:
        data = {"max_retry": 5, "same_error_hash_limit": 2}
        data.update(overrides)
        path = self.tmp / "policy.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return retry_manager.RetryManager(Policy.load(path), self.tmp / "retry")

    def test_timestamps_and_paths_do_not_change_identity(self):
        a = "ERROR: build failed at 2026-01-01T10:00:00Z in /home/a/project/x.gd"
        b = "ERROR: build failed at 2026-02-02T23:59:59Z in /home/b/project/x.gd"
        self.assertEqual(retry_manager.error_hash(a), retry_manager.error_hash(b))

    def test_distinct_errors_stay_distinct(self):
        self.assertNotEqual(
            retry_manager.error_hash("ERROR: missing export template"),
            retry_manager.error_hash("ERROR: gradle assembleDebug failed"))

    def test_repeated_error_stops_retrying(self):
        rm = self._rm()
        rm.record_failure("t", "ERROR: same thing at 10:00:00")
        decision = rm.record_failure("t", "ERROR: same thing at 11:30:00")
        self.assertEqual(decision.decision, retry_manager.ROOT_CAUSE_ANALYSIS)

    def test_budget_exhaustion_escalates_to_human(self):
        rm = self._rm()
        for i in range(5):
            decision = rm.record_failure("t", f"ERROR: distinct failure {i} abcdef")
        self.assertEqual(decision.decision, retry_manager.NEEDS_HUMAN_REVIEW)

    def test_ledger_survives_restart(self):
        self._rm().record_failure("t", "ERROR: one")
        self.assertEqual(len(self._rm().attempts("t")), 1)


class TestLicenseManager(TempCase):
    def _lm(self) -> LicenseManager:
        return LicenseManager(self.tmp / "LICENSE_REGISTRY.json")

    def test_approved_requires_verifier_and_commercial_use(self):
        lm = self._lm()
        with self.assertRaises(ValueError):
            lm.register(LicenseEntry(id="a", name="a", type="asset", source="s",
                                     status=APPROVED, commercial_use=True))
        with self.assertRaises(ValueError):
            lm.register(LicenseEntry(id="b", name="b", type="asset", source="s",
                                     status=APPROVED, verified_by="me",
                                     commercial_use=None))

    def test_unknown_blocks_release(self):
        lm = self._lm()
        lm.register(LicenseEntry(id="u", name="u", type="model_weights", source="s",
                                 status=UNKNOWN))
        gate = lm.release_gate(["u"])
        self.assertFalse(gate["release_allowed"])

    def test_unregistered_asset_blocks_release(self):
        gate = self._lm().release_gate(["never_seen"])
        self.assertFalse(gate["release_allowed"])

    def test_approved_asset_passes_and_reports_attribution(self):
        lm = self._lm()
        lm.register(LicenseEntry(id="ok", name="ok", type="asset", source="s",
                                 license="CC0", commercial_use=True,
                                 attribution_required=True, status=APPROVED,
                                 verified_by="tester"))
        gate = lm.release_gate(["ok"])
        self.assertTrue(gate["release_allowed"])
        self.assertEqual(gate["attribution_required"], ["ok"])

    def test_code_and_weight_licences_are_separate_fields(self):
        lm = self._lm()
        lm.register(LicenseEntry(id="m", name="m", type="model_weights", source="s",
                                 code_license="MIT", weights_license="UNVERIFIED",
                                 status=UNKNOWN))
        entry = lm.get("m")
        self.assertEqual(entry["code_license"], "MIT")
        self.assertEqual(entry["weights_license"], "UNVERIFIED")
        self.assertFalse(lm.is_production_usable("m")[0])


class TestArtifactValidator(TempCase):
    def test_empty_file_is_not_acceptable(self):
        p = self.tmp / "empty.txt"
        p.touch()
        self.assertFalse(artifact_validator.file_exists(p)["ok"])

    def test_fake_apk_rejected(self):
        p = self.tmp / "fake.apk"
        p.write_text("not a zip", encoding="utf-8")
        self.assertFalse(artifact_validator.apk_valid(p)["ok"])

    def test_missing_apk_rejected(self):
        self.assertFalse(artifact_validator.apk_valid(self.tmp / "none.apk")["ok"])

    def test_zip_without_manifest_rejected(self):
        import zipfile
        p = self.tmp / "nomanifest.apk"
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("hello.txt", "hi")
        result = artifact_validator.apk_valid(p)
        self.assertTrue(result["is_zip"])
        self.assertFalse(result["ok"])

    def test_error_lines_detected(self):
        text = "loading\nSCRIPT ERROR: Parse Error: bad token\ndone"
        result = artifact_validator.text_contains_no_errors(text)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_count"], 1)

    def test_godot_project_detects_broken_reference(self):
        root = self.tmp / "proj"
        (root / "scenes").mkdir(parents=True)
        (root / "project.godot").write_text(
            'config/name="T"\nrun/main_scene="res://scenes/main.tscn"\n',
            encoding="utf-8")
        (root / "scenes/main.tscn").write_text(
            '[gd_scene]\n[ext_resource path="res://missing.png"]\n', encoding="utf-8")
        result = artifact_validator.godot_project_valid(root)
        self.assertFalse(result["ok"])
        self.assertTrue(result["broken_resource_refs"])


class TestLogRedaction(unittest.TestCase):
    def test_secrets_are_masked(self):
        text = ("token=abcdef123456 sk-abcdefgh12345678 "
                '"access_token": "ya29.something-long"')
        redacted = logging_setup.redact(text)
        self.assertNotIn("abcdef123456", redacted)
        self.assertNotIn("sk-abcdefgh12345678", redacted)
        self.assertNotIn("ya29.something-long", redacted)
        self.assertIn("REDACTED", redacted)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestTaskQueueClaimById(TempCase):
    def _queue(self) -> TaskQueue:
        return TaskQueue(self.tmp / "tasks.sqlite3")

    def test_claim_by_id_ignores_priority(self):
        q = self._queue()
        q.enqueue(Task(task_id="urgent", goal="a", priority=1))
        q.enqueue(Task(task_id="mine", goal="b", priority=500))
        self.assertEqual(q.claim("mine").status, "RUNNING")
        self.assertEqual(q.get("urgent").status, "QUEUED")

    def test_claim_rejects_non_queued_task(self):
        q = self._queue()
        q.enqueue(Task(task_id="t", goal="g"))
        q.claim("t")
        with self.assertRaises(ValueError):
            q.claim("t")

    def test_claim_unknown_task_raises(self):
        with self.assertRaises(KeyError):
            self._queue().claim("nope")
