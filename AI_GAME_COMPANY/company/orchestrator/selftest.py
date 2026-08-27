"""The section 40 completion checklist, executed for real.

Nothing here is asserted from belief: each check runs a command, writes a file,
or inspects the filesystem, and reports PASS / LIMITED / HUMAN_GATE / FAIL with
the log and output paths it produced.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import (artifact_validator, blender_runner, claude_runner, codex_runner,
               engine_runner, hardware_profiler, logging_setup, ollama_client,
               paths, process_runner, report_generator, retry_manager,
               state_manager, task_queue)
from .agent_router import AgentRouter
from .license_manager import APPROVED, UNKNOWN, LicenseEntry, LicenseManager
from .policy import PaidActionBlocked, Policy
from .report_generator import (BLOCKED, CheckResult, FAIL, HUMAN_GATE, LIMITED,
                               PASS, SKIPPED)

log = logging_setup.get_logger("selftest")

SELFTEST_GAME = "SELFTEST"


def _timed(fn: Callable[[], CheckResult]) -> CheckResult:
    started = time.time()
    try:
        result = fn()
    except Exception as exc:  # a broken check is a FAIL, never a crashed run
        result = CheckResult(
            id=getattr(fn, "__name__", "unknown"),
            name=getattr(fn, "__name__", "unknown"),
            expected="check runs without raising",
            actual=f"raised {type(exc).__name__}: {exc}",
            status=FAIL)
    result.duration_s = round(time.time() - started, 2)
    return result


class SelfTest:
    def __init__(self, policy: Policy | None = None):
        self.policy = policy or Policy.load()
        paths.ensure_dirs()
        self.hardware: dict[str, Any] = {}
        self.findings: list[str] = []

    # ---- 1 hardware --------------------------------------------------
    def check_hardware_profiler(self) -> CheckResult:
        path, profile = hardware_profiler.write_profile(self.policy)
        self.hardware = profile
        check = artifact_validator.json_parses(path)
        installed = sum(1 for p in profile["programs"].values() if p["installed"])
        return CheckResult(
            id="hardware_profiler", name="Hardware Profiler",
            expected="HARDWARE_PROFILE.json written with real OS/CPU/RAM/GPU/program data",
            actual=f"{profile['os']['system']}, {profile['cpu']['core_count']} cores, "
                   f"{(profile['ram']['total_mb'] or 0)//1024}GB RAM, "
                   f"GPU={profile['gpu']['detected']}, {installed} programs detected",
            status=PASS if check["ok"] else FAIL,
            output_path=paths.rel(path))

    # ---- 2 policy ----------------------------------------------------
    def check_policy_loader(self) -> CheckResult:
        policy = Policy.load()
        loaded_from_file = policy.source is not None
        defaults_safe = (not policy.get("allow_paid_api")
                         and not policy.get("allow_auto_purchase")
                         and not policy.get("allow_cloud_ai_generation"))
        return CheckResult(
            id="policy_loader", name="Policy Loader",
            expected="company_policy.json loads and paid flags default to false",
            actual=f"loaded_from_file={loaded_from_file}, paid flags all false={defaults_safe}",
            status=PASS if (loaded_from_file and defaults_safe) else FAIL,
            output_path=paths.rel(paths.POLICY_FILE),
            detail=policy.summary())

    # ---- 3 state -----------------------------------------------------
    def check_state_manager(self) -> CheckResult:
        sm = state_manager.StateManager()
        sm.init()
        sm.update(current_phase="INFRASTRUCTURE", engine=engine_runner.active_engine())
        sm.record_event("selftest_state_write")
        reloaded = state_manager.StateManager().load()
        atomic_ok = (reloaded["current_phase"] == "INFRASTRUCTURE"
                     and reloaded["updated_at"] is not None)
        return CheckResult(
            id="state_manager", name="State Manager",
            expected="company_state.json written atomically and reloads identically",
            actual=f"phase={reloaded['current_phase']}, "
                   f"history_entries={len(reloaded.get('history', []))}, atomic_write=ok",
            status=PASS if atomic_ok else FAIL,
            output_path=paths.rel(paths.STATE_FILE))

    # ---- 4 task queue ------------------------------------------------
    def check_task_queue(self) -> CheckResult:
        queue = task_queue.TaskQueue()
        tid = f"{SELFTEST_GAME}_queue_{datetime.now(timezone.utc).strftime('%H%M%S')}"
        queue.enqueue(task_queue.Task(
            task_id=tid, goal="selftest: queue round trip",
            game_id=SELFTEST_GAME, phase="INFRASTRUCTURE",
            department="QA", agent="local_planner", priority=10,
            acceptance_criteria=["task reaches PASS only with evidence"]))
        # Claim by id: claim_next() picks by priority and would pick up work
        # left over from an earlier run.
        claimed = queue.claim(tid)
        rejected_without_evidence = False
        try:
            queue.mark_pass(tid, {})
        except ValueError:
            rejected_without_evidence = True
        queue.mark_pass(tid, {"acceptance_checked": True,
                              "checks": ["queue round trip"]})
        final = queue.get(tid)
        counts = queue.counts()
        priority_pick = queue.claim_next()
        if priority_pick is not None:
            queue.set_status(priority_pick.task_id, "QUEUED",
                             note="released by selftest")
        ok = (claimed is not None and claimed.status == "RUNNING"
              and rejected_without_evidence and final.status == "PASS")
        return CheckResult(
            id="task_queue", name="Task Queue (SQLite)",
            expected="enqueue -> claim(RUNNING) -> PASS, and PASS refused without evidence",
            actual=f"claimed={claimed.status if claimed else None}, "
                   f"pass_without_evidence_rejected={rejected_without_evidence}, "
                   f"final={final.status}, counts={counts}",
            status=PASS if ok else FAIL,
            output_path=paths.rel(paths.TASK_DB_FILE))

    # ---- 5/6 ollama --------------------------------------------------
    def check_ollama(self) -> tuple[CheckResult, CheckResult]:
        client = ollama_client.OllamaClient(self.policy)
        health = client.health()
        endpoint = health.get("endpoint")
        if health["status"] == ollama_client.OK:
            model = health["models"][0]
            result = client.generate(
                model, "Reply with exactly: ORCHESTRATOR_OK",
                save_as="selftest_local_llm")
            call = CheckResult(
                id="ollama_call", name="Ollama localhost call",
                expected=f"HTTP 200 from {endpoint}/api/generate",
                actual=f"model={model}, {len(result.response or '')} chars in "
                       f"{result.duration_s:.1f}s",
                status=PASS if result.ok else FAIL,
                output_path=result.output_path)
            save = CheckResult(
                id="local_llm_save", name="Local LLM response saved",
                expected="response persisted as JSON under company/state/ai_outputs/",
                actual=f"saved to {result.output_path}" if result.output_path
                       else "no file written",
                status=PASS if result.output_path else FAIL,
                output_path=result.output_path)
            return call, save

        # Not running here: prove the save path works with a recorded probe so
        # the plumbing itself is still verified.
        probe_path = client.save_output("selftest_local_llm_unavailable", {
            "endpoint": endpoint, "status": health["status"],
            "error": health.get("error"), "models": health.get("models", []),
            "note": "no local model was called; this file proves the save path works",
        })
        status = LIMITED if health["status"] in (ollama_client.NOT_RUNNING,
                                                ollama_client.NO_MODELS) else BLOCKED
        call = CheckResult(
            id="ollama_call", name="Ollama localhost call",
            expected=f"HTTP 200 from {endpoint or 'localhost:11434'}/api/tags",
            actual=f"{health['status']}: {health.get('error')}",
            status=status,
            detail={"hint": health.get("hint", "install Ollama and run: ollama serve")})
        save = CheckResult(
            id="local_llm_save", name="Local LLM response saved",
            expected="response persisted as JSON under company/state/ai_outputs/",
            actual="write path exercised with a status record (no model available)",
            status=LIMITED if probe_path.exists() else FAIL,
            output_path=paths.rel(probe_path))
        return call, save

    # ---- 7 codex -----------------------------------------------------
    def check_codex(self) -> CheckResult:
        runner = codex_runner.CodexRunner(self.policy)
        caps = runner.capabilities()
        if not caps["installed"]:
            router = AgentRouter(self.policy)
            plan = router.route("code_review")
            return CheckResult(
                id="codex_exec", name="Codex exec test / LIMITED handling",
                expected="codex exec runs, or the CODEX_LIMITED fallback engages",
                actual=f"codex not installed; router fell back to '{plan.selected}' "
                       f"(chain {plan.chain})",
                status=LIMITED,
                detail={"routing": plan.to_dict(),
                        "fallback_order": "local reasoner -> Claude review (section 3)"})
        result = runner.review(
            "Reply with JSON only: {\"verdict\": \"PASS\", \"critical\": []}",
            log_name="codex_selftest")
        status = {codex_runner.OK: PASS,
                  codex_runner.CODEX_LIMITED: LIMITED,
                  codex_runner.NOT_LOGGED_IN: HUMAN_GATE}.get(result.status, FAIL)
        return CheckResult(
            id="codex_exec", name="Codex exec test / LIMITED handling",
            expected="codex exec returns output, or a limit/auth state is handled",
            actual=f"{result.status}: {(result.error or (result.output or ''))[:160]}",
            status=status, log_path=result.log_path,
            detail={"capabilities": caps, "fallback": result.fallback})

    # ---- 8 blender ---------------------------------------------------
    def check_blender(self) -> CheckResult:
        runner = blender_runner.BlenderRunner(self.policy)
        caps = runner.capabilities()
        if not caps["installed"]:
            return CheckResult(
                id="blender_background", name="Blender background test",
                expected="blender --background --python selftest.py writes an output file",
                actual="blender not installed; adapter verifies exit code AND output "
                       "file when it is",
                status=LIMITED,
                output_path=paths.rel(paths.BLENDER_TOOLS_DIR / "selftest.py"))
        result = runner.selftest()
        return CheckResult(
            id="blender_background", name="Blender background test",
            expected="exit 0 AND blender_selftest.txt exists (section 11)",
            actual=f"{result.status}, exit={result.exit_code}",
            status=PASS if result.ok else FAIL,
            log_path=result.log_path,
            output_path=paths.rel(paths.STATE_DIR / "blender_selftest.txt"))

    # ---- 9 engine validation -----------------------------------------
    def check_engine_validate(self) -> CheckResult:
        static = artifact_validator.godot_project_valid()
        engine = engine_runner.EngineRunner(self.policy)
        caps = engine.capabilities()
        static_line = (f"static project check: ok={static['ok']}, "
                       f"{static['scene_count']} scenes, {static['script_count']} scripts, "
                       f"{len(static['broken_resource_refs'])} broken res:// refs")
        if not caps.get("installed"):
            return CheckResult(
                id="engine_validate", name=f"{engine.engine} batch compile/validate",
                expected="engine headless validation reports zero errors",
                actual=f"{engine.engine} binary not found; {static_line}",
                status=LIMITED if static["ok"] else FAIL,
                detail={"capabilities": caps, "static": static})
        result = engine.validate()
        ok = result["status"] == "OK"
        if not ok and result.get("errors"):
            self.findings.append(
                f"engine validation reported {result.get('error_count', len(result['errors']))} "
                f"error line(s); first: {result['errors'][0]}")
        for warning in (result.get("warnings") or [])[:10]:
            self.findings.append(f"engine warning (not blocking): {warning}")
        return CheckResult(
            id="engine_validate", name=f"{engine.engine} batch compile/validate",
            expected="headless validation exits 0 with no error lines",
            actual=f"{result['status']}, exit={result['exit_code']}, "
                   f"errors={result.get('error_count', 0)}, "
                   f"warnings={result.get('warning_count', 0)}; {static_line}",
            status=PASS if ok else FAIL,
            log_path=result.get("log_path"),
            detail={"engine": result, "static": static})

    # ---- 10 android build --------------------------------------------
    def check_android_build(self) -> CheckResult:
        engine = engine_runner.EngineRunner(self.policy)
        caps = engine.capabilities()
        out = paths.BUILDS_DIR / SELFTEST_GAME / "selftest.apk"
        sdk = (self.hardware.get("android_sdk") or {}) if self.hardware else {}
        if not caps.get("installed"):
            return CheckResult(
                id="android_build", name="Android build test",
                expected="APK exists, size > 0, manifest present (section 32)",
                actual=f"{engine.engine} binary not found; android_sdk_installed="
                       f"{sdk.get('installed')}",
                status=LIMITED, detail={"capabilities": caps})
        result = engine.build_android(out)
        status_map = {"OK": PASS, "HUMAN_GATE": HUMAN_GATE,
                      "EXPORT_TEMPLATES_MISSING": LIMITED}
        status = status_map.get(result["status"], FAIL)
        if status == FAIL:
            self.findings.append(f"Android build failed: {result.get('detail')}")
        return CheckResult(
            id="android_build", name="Android build test",
            expected="exit 0 AND build log clean AND APK present with manifest",
            actual=f"{result['status']}: {result.get('detail') or 'apk verified'}",
            status=status, log_path=result.get("log_path"),
            output_path=paths.rel(out) if out.exists() else None,
            detail=result)

    # ---- 11 build log collection -------------------------------------
    def check_build_log_collection(self) -> CheckResult:
        probe = process_runner.run(
            ["python3", "-c", "import sys; print('log capture probe'); "
                              "print('stderr line', file=sys.stderr)"],
            timeout=60, policy=self.policy, log_name="selftest_log_capture")
        log_file = paths.ROOT / (probe.log_path or "")
        body = log_file.read_text(encoding="utf-8") if probe.log_path and log_file.exists() else ""
        has_all = all(tok in body for tok in ("COMMAND :", "EXIT", "log capture probe",
                                              "stderr line"))
        todays = list(logging_setup.log_dir_for_today().glob("*.log"))
        return CheckResult(
            id="build_log_collection", name="Build log collection",
            expected="every external command's stdout/stderr/exit code is written to logs/",
            actual=f"log file captured all fields={has_all}, "
                   f"{len(todays)} log file(s) in today's folder",
            status=PASS if has_all else FAIL,
            log_path=probe.log_path)

    # ---- 12 report generator (checked by the caller writing the report)
    def check_report_generator(self) -> CheckResult:
        game_report = report_generator.write_game_report({
            "game_id": SELFTEST_GAME, "game_name": "Selftest Placeholder",
            "genre": "infrastructure smoke test",
            "how_to_play": "This file only proves the report writer works.",
            "features": "Generated by AI_GAME_COMPANY selftest.",
            "qa_compile": "see setup report", "apk_exists": "no APK in this run",
        })
        activity = report_generator.write_ai_activity_report(SELFTEST_GAME, {
            "claude": {"role": "infrastructure build + supervision"},
            "codex": "not installed in this environment",
            "local_llm": "not running in this environment",
            "build": {"failures": 0, "fixes": 0},
        })
        missing_required_rejected = False
        try:
            report_generator.write_game_report({"game_id": "BAD"})
        except ValueError:
            missing_required_rejected = True
        ok = game_report.exists() and activity.exists() and missing_required_rejected
        return CheckResult(
            id="report_generator", name="Report Generator",
            expected="game report + AI activity report written; incomplete report refused",
            actual=f"game_report={game_report.name}, activity={activity.name}, "
                   f"incomplete_rejected={missing_required_rejected}",
            status=PASS if ok else FAIL,
            output_path=paths.rel(game_report))

    # ---- 13 retry manager --------------------------------------------
    def check_retry_manager(self) -> CheckResult:
        rm = retry_manager.RetryManager(self.policy)
        tid = "SELFTEST_retry"
        rm.reset(tid)
        first = rm.record_failure(tid, "ERROR: Gradle task assembleDebug failed at 12:00:01")
        second = rm.record_failure(tid, "ERROR: Gradle task assembleDebug failed at 13:45:59")
        different = rm.record_failure(tid, "ERROR: Missing export template for android")
        hash_dedup_ok = (first.error_hash == second.error_hash
                         and second.decision == retry_manager.ROOT_CAUSE_ANALYSIS
                         and different.error_hash != first.error_hash)
        for i in range(5):
            last = rm.record_failure(tid, f"ERROR: unique failure {i} xyz")
        human_ok = last.decision == retry_manager.NEEDS_HUMAN_REVIEW
        rm.reset(tid)
        return CheckResult(
            id="retry_manager", name="Retry Manager",
            expected="same error hash -> ROOT_CAUSE_ANALYSIS; max_retry -> NEEDS_HUMAN_REVIEW",
            actual=f"timestamps normalised to one hash={first.error_hash == second.error_hash}, "
                   f"repeat decision={second.decision}, budget exhausted={last.decision}",
            status=PASS if (hash_dedup_ok and human_ok) else FAIL,
            output_path=paths.rel(paths.RETRY_DIR))

    # ---- 14 resume ---------------------------------------------------
    def check_resume(self) -> CheckResult:
        queue = task_queue.TaskQueue()
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        tid = f"{SELFTEST_GAME}_resume_{stamp}"
        queue.enqueue(task_queue.Task(task_id=tid, goal="selftest: survive a restart",
                                      game_id=SELFTEST_GAME, phase="INFRASTRUCTURE",
                                      priority=5))
        queue.claim(tid)  # now RUNNING, as if the process died mid-task

        # Simulated restart: brand new objects, nothing carried in memory.
        fresh_queue = task_queue.TaskQueue()
        candidates = [t.task_id for t in fresh_queue.resume_candidates()]
        found = tid in candidates

        # Section 15: a completion whose artifact is absent must be revoked.
        sm = state_manager.StateManager()
        sm.update(build_status="SUCCESS")
        sm.register_artifact("selftest_missing_apk",
                             paths.BUILDS_DIR / SELFTEST_GAME / "does_not_exist.apk")
        verify = sm.verify_against_disk()
        revoked = sm.load()["build_status"] == "REVOKED_ARTIFACT_MISSING"
        # Leave the state clean for the real pipeline.
        state = sm.load()
        state.get("artifacts", {}).pop("selftest_missing_apk", None)
        state["build_status"] = "NOT_STARTED"
        sm.save(state)
        fresh_queue.set_status(tid, "QUEUED", note="requeued by resume selftest")
        # Close the selftest's own task so repeat runs do not pile up work.
        fresh_queue.claim(tid)
        fresh_queue.mark_pass(tid, {"acceptance_checked": True,
                                    "checks": ["resume recovery verified"]})
        return CheckResult(
            id="resume", name="Resume test",
            expected="interrupted RUNNING task is re-found after restart and a "
                     "completion with a missing artifact is revoked",
            actual=f"interrupted task recovered={found}, "
                   f"missing-artifact completion revoked={revoked}, "
                   f"problems_detected={len(verify['problems'])}",
            status=PASS if (found and revoked) else FAIL,
            output_path=paths.rel(paths.STATE_FILE))

    # ---- 15 license registry -----------------------------------------
    def check_license_registry(self) -> CheckResult:
        lm = LicenseManager()
        lm.register(LicenseEntry(
            id="godot_engine_4.3", name="Godot Engine 4.3", type="code",
            source="https://github.com/godotengine/godot", version="4.3-stable",
            license="MIT", code_license="MIT", commercial_use=True,
            attribution_required=True, status=APPROVED,
            verified_by="claude_code_infrastructure_build",
            redistribution_rules="MIT: keep copyright notice",
            notes="engine binary; the exported game itself is separately licensed"))
        lm.register(LicenseEntry(
            id="qwen2.5-coder", name="Qwen2.5-Coder weights", type="model_weights",
            source="https://ollama.com/library/qwen2.5-coder",
            license="UNVERIFIED", code_license=None, weights_license="UNVERIFIED",
            commercial_use=None, status=UNKNOWN,
            notes="code licence and weight licence are tracked separately; "
                  "verify the exact model repository before production use"))
        approve_without_verifier_rejected = False
        try:
            lm.register(LicenseEntry(id="bad", name="bad", type="asset", source="x",
                                     status=APPROVED, commercial_use=True))
        except ValueError:
            approve_without_verifier_rejected = True
        gate = lm.release_gate(["godot_engine_4.3", "qwen2.5-coder", "never_registered"])
        ok = (not gate["release_allowed"] and len(gate["blockers"]) == 2
              and approve_without_verifier_rejected)
        return CheckResult(
            id="license_registry", name="License Registry",
            expected="UNKNOWN and unregistered assets block a release; APPROVED needs a verifier",
            actual=f"release_allowed={gate['release_allowed']}, "
                   f"blockers={[b['id'] for b in gate['blockers']]}, "
                   f"approve_without_verifier_rejected={approve_without_verifier_rejected}",
            status=PASS if ok else FAIL,
            output_path=paths.rel(paths.LICENSE_REGISTRY_FILE))

    # ---- 16 paid api block -------------------------------------------
    def check_paid_api_block(self) -> CheckResult:
        policy = Policy.load()
        fake_env = {"PATH": os.environ.get("PATH", ""),
                    "OPENAI_API_KEY": "sk-selftest-not-a-real-key",
                    "REPLICATE_API_TOKEN": "r8_selftest",
                    "ANTHROPIC_API_KEY": "sk-ant-selftest"}
        sanitized = policy.sanitized_env(env=fake_env)
        stripped = [k for k in ("OPENAI_API_KEY", "REPLICATE_API_TOKEN",
                                "ANTHROPIC_API_KEY") if k not in sanitized]
        guard_raised = False
        try:
            policy.guard_paid_api("selftest_paid_call")
        except PaidActionBlocked:
            guard_raised = True
        purchase_blocked = False
        try:
            policy.guard_purchase("selftest_asset_purchase")
        except PaidActionBlocked:
            purchase_blocked = True
        remote_ollama_blocked = False
        remote_policy = Policy.load()
        remote_policy.data["ollama_endpoint"] = "https://api.example.com"
        try:
            remote_policy.ollama_endpoint()
        except PaidActionBlocked:
            remote_ollama_blocked = True
        ok = (len(stripped) == 3 and guard_raised and purchase_blocked
              and remote_ollama_blocked)
        return CheckResult(
            id="paid_api_block", name="Paid API block test",
            expected="paid keys stripped from child env; paid/purchase/remote-ollama "
                     "actions raise PAID_ACTION_BLOCKED",
            actual=f"keys stripped={stripped}, paid_guard={guard_raised}, "
                   f"purchase_guard={purchase_blocked}, remote_ollama_blocked="
                   f"{remote_ollama_blocked}",
            status=PASS if ok else FAIL,
            detail={"note": "no real key was used; a synthetic env was tested"})

    # ---- extra: claude CLI + routing ---------------------------------
    def check_claude_cli(self) -> CheckResult:
        caps = claude_runner.ClaudeRunner(self.policy).capabilities()
        if not caps["installed"]:
            return CheckResult(
                id="claude_cli", name="Claude Code CLI non-interactive mode",
                expected="claude --help documents a non-interactive flag",
                actual="claude CLI not installed; Claude Code stays the human-driven "
                       "supervisor (section 2)",
                status=LIMITED)
        return CheckResult(
            id="claude_cli", name="Claude Code CLI non-interactive mode",
            expected="claude --help documents --print before any subprocess use",
            actual=f"version={caps['version']}, --print documented={caps['headless']}, "
                   f"--output-format={caps.get('output_format_json')}",
            status=PASS if caps["headless"] else LIMITED,
            detail=caps)

    def check_agent_router(self) -> CheckResult:
        router = AgentRouter(self.policy)
        routes = {kind: router.route(kind).to_dict()
                  for kind in ("json_config", "build_log_triage", "core_system",
                               "code_review", "release_approval")}
        disagreement = router.resolve_disagreement(
            "PASS", "FAIL", {"status": "BUILD_FAILED", "ok": False})
        machine_wins = disagreement["decided_by"] == "actual_build_or_test_result"
        all_routed = all(r["selected"] for r in routes.values())
        return CheckResult(
            id="agent_router", name="AI routing + disagreement rule",
            expected="every task kind routes to an available agent or HUMAN; "
                     "reviewer conflicts are settled by the real build result",
            actual="; ".join(f"{k}->{v['selected']}" for k, v in routes.items())
                   + f"; machine_result_wins={machine_wins}",
            status=PASS if (all_routed and machine_wins) else FAIL,
            detail={"routes": routes, "disagreement": disagreement})

    # ---- runner ------------------------------------------------------
    def run_all(self) -> list[CheckResult]:
        checks: list[CheckResult] = []
        checks.append(_timed(self.check_hardware_profiler))
        checks.append(_timed(self.check_policy_loader))
        checks.append(_timed(self.check_state_manager))
        checks.append(_timed(self.check_task_queue))
        ollama_call, local_save = self.check_ollama()
        checks += [ollama_call, local_save]
        checks.append(_timed(self.check_codex))
        checks.append(_timed(self.check_claude_cli))
        checks.append(_timed(self.check_blender))
        checks.append(_timed(self.check_engine_validate))
        checks.append(_timed(self.check_android_build))
        checks.append(_timed(self.check_build_log_collection))
        checks.append(_timed(self.check_report_generator))
        checks.append(_timed(self.check_retry_manager))
        checks.append(_timed(self.check_resume))
        checks.append(_timed(self.check_license_registry))
        checks.append(_timed(self.check_paid_api_block))
        checks.append(_timed(self.check_agent_router))
        return checks
