"""Tests for the orchestrator core.

Run:  python3 AI_GAME_COMPANY/tests/test_orchestrator.py

Deliberately stdlib-only unittest: section 13 says start simple, and adding a
pytest dependency to a machine we are still bootstrapping buys nothing here.

These tests target the RULES, not the plumbing - the places where the master
prompt says something must be refused. A queue that lets a task reach PASS
without evidence, or a policy that opens up when its file goes missing, would
still "work" while breaking the guarantees the whole design rests on.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.orchestrator.hardware import HardwareProfile  # noqa: E402
from company.orchestrator.policy import Policy, PolicyViolation  # noqa: E402
from company.orchestrator.state import CompanyState  # noqa: E402
from company.orchestrator.tasks import AcceptanceNotVerified, Task, TaskQueue  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_POLICY = REPO_ROOT / "AI_GAME_COMPANY" / "config" / "company_policy.json"


class PolicyTests(unittest.TestCase):
    def test_missing_policy_denies_everything(self):
        policy = Policy.deny_all()
        self.assertFalse(policy.allows("allow_paid_api"))
        with self.assertRaises(PolicyViolation):
            policy.require("allow_paid_api", "calling a billed API")

    def test_unknown_key_is_denied_not_allowed(self):
        policy = Policy(raw={"allow_paid_api": False})
        self.assertFalse(policy.allows("some_key_nobody_defined"))

    def test_only_literal_true_allows(self):
        # "true" the string, or 1, must not count as permission to spend money.
        for value in ("true", 1, "yes", [], {}):
            self.assertFalse(Policy(raw={"allow_paid_api": value}).allows("allow_paid_api"))
        self.assertTrue(Policy(raw={"allow_paid_api": True}).allows("allow_paid_api"))

    def test_env_key_presence_is_reported_not_used(self):
        policy = Policy(raw={"blocked_env_keys": ["OPENAI_API_KEY", "FAL_KEY"]})
        found = policy.check_env_for_paid_keys(
            {"OPENAI_API_KEY": "sk-secret-value", "UNRELATED": "x"}
        )
        self.assertEqual(found, ["OPENAI_API_KEY"])
        # The value must never come back out of this call.
        self.assertNotIn("sk-secret-value", "".join(found))

    def test_build_needs_all_three_checks(self):
        policy = Policy.load(REAL_POLICY)
        policy.assert_build_verification(True, True, True)
        for combo in ((False, True, True), (True, False, True), (True, True, False)):
            with self.assertRaises(PolicyViolation):
                policy.assert_build_verification(*combo)

    def test_real_policy_blocks_spending(self):
        policy = Policy.load(REAL_POLICY)
        self.assertFalse(policy.allows("allow_paid_api"))
        self.assertFalse(policy.allows("allow_auto_purchase"))
        self.assertFalse(policy.allows("allow_paid_assets"))
        self.assertIn("unity", policy.never_auto_install())
        self.assertIn("ollama_models", policy.never_auto_install())


class TaskQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.queue = TaskQueue(Path(self.tmp.name) / "tasks.db")

    def tearDown(self):
        self.queue.close()
        self.tmp.cleanup()

    def test_pass_refused_without_evidence(self):
        self.queue.add(Task(task_id="T1", goal="do a thing"))
        with self.assertRaises(AcceptanceNotVerified):
            self.queue.mark_pass("T1")
        self.assertEqual(self.queue.get("T1")["status"], "QUEUED")

    def test_pass_refused_when_declared_output_missing(self):
        missing = str(Path(self.tmp.name) / "never_written.apk")
        self.queue.add(Task(task_id="T2", goal="build", output_paths=[missing]))
        with self.assertRaises(AcceptanceNotVerified):
            self.queue.mark_pass("T2")

    def test_pass_refused_when_output_is_empty_file(self):
        empty = Path(self.tmp.name) / "empty.apk"
        empty.touch()
        self.queue.add(Task(task_id="T3", goal="build", output_paths=[str(empty)]))
        with self.assertRaises(AcceptanceNotVerified):
            self.queue.mark_pass("T3")

    def test_pass_allowed_with_real_output(self):
        real = Path(self.tmp.name) / "real.apk"
        real.write_bytes(b"not empty")
        self.queue.add(Task(task_id="T4", goal="build", output_paths=[str(real)]))
        self.queue.mark_pass("T4")
        self.assertEqual(self.queue.get("T4")["status"], "PASS")

    def test_claim_next_respects_priority(self):
        self.queue.add(Task(task_id="low", goal="later", priority=200))
        self.queue.add(Task(task_id="high", goal="sooner", priority=10))
        self.assertEqual(self.queue.claim_next()["task_id"], "high")

    def test_retry_escalates_at_limit(self):
        self.queue.add(Task(task_id="R1", goal="flaky", max_retry=2))
        self.assertEqual(self.queue.mark_failed("R1", "boom"), "QUEUED")
        self.assertEqual(self.queue.mark_failed("R1", "boom again"), "NEEDS_HUMAN_REVIEW")

    def test_repeated_error_hash_stops_burning_retries(self):
        # Section 31: the same failure twice means retrying is pointless.
        self.queue.add(Task(task_id="R2", goal="same error", max_retry=5))
        self.assertEqual(self.queue.mark_failed("R2", "CS1069", error_hash="h1"), "QUEUED")
        self.assertEqual(
            self.queue.mark_failed("R2", "CS1069", error_hash="h1"), "NEEDS_HUMAN_REVIEW"
        )
        self.assertLess(self.queue.get("R2")["retry_count"], 5)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = CompanyState(path=self.root / "state.json", data=CompanyState.blank())

    def tearDown(self):
        self.tmp.cleanup()

    def test_complete_without_apk_is_revoked(self):
        # The exact scenario section 15 calls out.
        self.state.data["games"]["game01"] = {"phase": "COMPLETE", "apk_path": "gone.apk"}
        self.state.data["build_status"] = "SUCCESS"

        found = self.state.verify_against_disk(self.root)

        self.assertTrue(found)
        self.assertEqual(self.state.data["games"]["game01"]["phase"], "ANDROID_BUILD")
        self.assertEqual(self.state.data["build_status"], "UNKNOWN")

    def test_complete_with_real_apk_survives(self):
        apk_dir = self.root / "Builds" / "game01" / "APK"
        apk_dir.mkdir(parents=True)
        (apk_dir / "Game01.apk").write_bytes(b"x" * 32)

        self.state.data["games"]["game01"] = {"phase": "COMPLETE"}
        self.assertEqual(self.state.verify_against_disk(self.root), [])
        self.assertEqual(self.state.data["games"]["game01"]["phase"], "COMPLETE")

    def test_zero_byte_apk_does_not_count(self):
        apk_dir = self.root / "Builds" / "game01" / "APK"
        apk_dir.mkdir(parents=True)
        (apk_dir / "Game01.apk").touch()

        self.state.data["games"]["game01"] = {"phase": "COMPLETE"}
        self.assertTrue(self.state.verify_against_disk(self.root))

    def test_early_phase_not_touched(self):
        self.state.data["games"]["game02"] = {"phase": "SCENARIO"}
        self.assertEqual(self.state.verify_against_disk(self.root), [])

    def test_unknown_phase_rejected(self):
        with self.assertRaises(ValueError):
            self.state.set_phase("game01", "SOMETHING_MADE_UP")

    def test_phase_progression(self):
        self.assertEqual(self.state.next_phase("game01"), "IDEA")
        self.state.set_phase("game01", "APK_VERIFY")
        self.assertEqual(self.state.next_phase("game01"), "REPORT")
        self.state.set_phase("game01", "COMPLETE")
        self.assertIsNone(self.state.next_phase("game01"))


class HardwareTests(unittest.TestCase):
    def _profile(self, ram_free: float, nvidia: bool) -> HardwareProfile:
        return HardwareProfile(raw={
            "hardware": {
                "cpu": "test cpu", "ramTotalGb": 16.0, "ramFreeGb": ram_free,
                "gpus": [{"name": "Intel Iris Xe"}],
                "nvidiaSmi": {"available": nvidia},
            },
            "tools": {"codex": {"installed": True, "status": "FOUND_BUT_NOT_RUNNABLE"}},
            "ollamaApi": {"reachable": True, "models": []},
            "unity": {"status": "OK", "matchingEditorPath": "C:/Unity.exe"},
        })

    def test_tier_scales_down_with_free_ram(self):
        self.assertEqual(self._profile(12.0, False).recommend_llm_tier()[0], "7b-q4")
        self.assertEqual(self._profile(6.0, False).recommend_llm_tier()[0], "3b-q4")
        self.assertEqual(self._profile(4.0, False).recommend_llm_tier()[0], "1.5b-q4")

    def test_no_tier_when_ram_exhausted(self):
        tier, why = self._profile(1.5, False).recommend_llm_tier()
        self.assertIsNone(tier)
        self.assertIn("no room", why)

    def test_integrated_gpu_blocks_image_generation(self):
        verdicts = {v.capability: v for v in self._profile(6.0, False).verdicts()}
        self.assertEqual(verdicts["local_image_generation"].status, "NOT_VIABLE")
        # It must also say what to do instead, not just refuse.
        self.assertIn("CC0", verdicts["local_image_generation"].recommendation)

    def test_installed_but_unrunnable_codex_is_unknown_not_viable(self):
        # Section 41 STEP 5: no verified command list means no adapter.
        verdicts = {v.capability: v for v in self._profile(6.0, False).verdicts()}
        self.assertEqual(verdicts["codex_review"].status, "UNKNOWN")

    def test_local_llm_limited_without_gpu(self):
        verdicts = {v.capability: v for v in self._profile(6.0, False).verdicts()}
        self.assertEqual(verdicts["local_llm"].status, "LIMITED")

    def test_real_profile_parses_if_present(self):
        path = REPO_ROOT / "AI_GAME_COMPANY" / "config" / "HARDWARE_PROFILE.json"
        if not path.exists():
            self.skipTest("no HARDWARE_PROFILE.json committed yet")
        profile = HardwareProfile.load(path)
        self.assertGreater(profile.ram_total_gb, 0)
        self.assertTrue(profile.verdicts())


if __name__ == "__main__":
    unittest.main(verbosity=2)
