"""AI_GAME_COMPANY orchestrator CLI (master prompt section 13).

Usage:
    python3 -m company.orchestrator.main doctor
    python3 -m company.orchestrator.main init
    python3 -m company.orchestrator.main selftest
    python3 -m company.orchestrator.main status
    python3 -m company.orchestrator.main engine validate
    python3 -m company.orchestrator.main engine build --out builds/Game01/game.apk
    python3 -m company.orchestrator.main task add --goal "..." --kind core_system
    python3 -m company.orchestrator.main task list
    python3 -m company.orchestrator.main resume
    python3 -m company.orchestrator.main license list

Run it from the AI_GAME_COMPANY directory (or set AI_GAME_COMPANY_ROOT).
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import (blender_runner, claude_runner, codex_runner, engine_runner,
               hardware_profiler, ollama_client, paths, report_generator,
               state_manager, task_queue)
from .agent_router import AgentRouter
from .license_manager import LicenseManager
from .policy import Policy
from .selftest import SelfTest


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


# ---------------------------------------------------------------- doctor
def cmd_doctor(args: argparse.Namespace) -> int:
    policy = Policy.load()
    paths.ensure_dirs()
    path, profile = hardware_profiler.write_profile(policy)
    engine = engine_runner.EngineRunner(policy)
    summary = {
        "company_root": str(paths.ROOT),
        "target_project": str(paths.target_project_root()),
        "os": profile["os"]["platform"],
        "cpu_cores": profile["cpu"]["core_count"],
        "ram_gb": round((profile["ram"]["total_mb"] or 0) / 1024, 1),
        "gpu": profile["gpu"]["name"] or "none detected",
        "disk_free_gb": profile["disk"]["free_gb"],
        "installed": sorted(n for n, p in profile["programs"].items() if p["installed"]),
        "missing": sorted(n for n, p in profile["programs"].items() if not p["installed"]),
        "android_sdk": profile["android_sdk"]["status"],
        "cli_capabilities": profile["cli_capabilities"],
        "model_recommendation": profile["model_recommendation"],
        "active_engine": engine.engine,
        "engine": engine.capabilities(),
        "other_engine": engine.other_engine_status(),
        "ollama": ollama_client.OllamaClient(policy).health(),
        "codex": codex_runner.CodexRunner(policy).capabilities(),
        "claude": claude_runner.ClaudeRunner(policy).capabilities(),
        "blender": blender_runner.BlenderRunner(policy).capabilities(),
        "policy": policy.summary(),
        "hardware_profile_path": paths.rel(path),
        "warnings": profile["warnings"],
    }
    _print_json(summary)
    return 0


# ------------------------------------------------------------------ init
def cmd_init(args: argparse.Namespace) -> int:
    paths.ensure_dirs()
    policy = Policy.load()
    sm = state_manager.StateManager()
    state = sm.init(force=args.force)
    task_queue.TaskQueue()
    LicenseManager()
    engine = engine_runner.EngineRunner(policy)
    sm.update(engine=engine.engine,
              engine_status=engine.capabilities().get("status", "UNKNOWN"))
    _print_json({
        "initialised": True,
        "company_root": str(paths.ROOT),
        "state_file": paths.rel(paths.STATE_FILE),
        "task_db": paths.rel(paths.TASK_DB_FILE),
        "license_registry": paths.rel(paths.LICENSE_REGISTRY_FILE),
        "engine": engine.engine,
        "current_phase": state["current_phase"],
    })
    return 0


# -------------------------------------------------------------- selftest
def cmd_selftest(args: argparse.Namespace) -> int:
    policy = Policy.load()
    paths.ensure_dirs()
    suite = SelfTest(policy)
    checks = suite.run_all()

    sm = state_manager.StateManager()
    sm.init()
    engine = engine_runner.EngineRunner(policy)
    by_id = {c.id: c for c in checks}
    sm.update(
        engine=engine.engine,
        engine_status=by_id["engine_validate"].status,
        ollama_status=by_id["ollama_call"].status,
        codex_status=by_id["codex_exec"].status,
        claude_status=by_id["claude_cli"].status,
        blender_status=by_id["blender_background"].status,
        build_status=by_id["android_build"].status,
        qa_status="SELFTEST_" + ("PASS" if not any(c.blocking for c in checks) else "FAIL"),
        current_phase="INFRASTRUCTURE",
    )

    environment_note = _environment_note(engine)
    report_path = report_generator.write_setup_report(
        checks,
        hardware=suite.hardware,
        policy_summary=policy.summary(),
        state_summary=sm.summary(),
        environment_note=environment_note,
        findings=suite.findings,
        next_steps=_next_steps(checks),
    )

    failed = [c.id for c in checks if c.blocking]
    limited = [c.id for c in checks if c.status == report_generator.LIMITED]
    gates = [c.id for c in checks if c.status == report_generator.HUMAN_GATE]
    print(f"\nreport: {paths.rel(report_path)}")
    print(f"PASS={sum(1 for c in checks if c.status == report_generator.PASS)} "
          f"LIMITED={len(limited)} HUMAN_GATE={len(gates)} FAIL={len(failed)}")
    for c in checks:
        print(f"  [{c.status:<10}] {c.name}: {c.actual[:120]}")
    if failed:
        print("\nFAILED:", ", ".join(failed))
    return 1 if failed else 0


def _environment_note(engine: engine_runner.EngineRunner) -> str:
    caps = engine.capabilities()
    return (
        f"- Host: `{platform.platform()}`\n"
        f"- Company root: `{paths.ROOT}`\n"
        f"- Target game project: `{paths.target_project_root()}`\n"
        f"- Active engine: **{engine.engine}** "
        f"(binary {'found: ' + str(caps.get('version')) if caps.get('installed') else 'NOT found'})\n"
        f"- Run at: {datetime.now(timezone.utc).isoformat()}\n\n"
        "This report describes the machine that executed it. Re-run "
        "`python3 -m company.orchestrator.main selftest` on the development PC to "
        "get that machine's real statuses - results are not transferable."
    )


def _next_steps(checks: list[report_generator.CheckResult]) -> list[str]:
    steps: list[str] = []
    by_id = {c.id: c for c in checks}
    if by_id["ollama_call"].status != report_generator.PASS:
        steps.append("Install Ollama on the development PC, run `ollama serve`, verify "
                     "the exact model licence, set it to APPROVED in "
                     "LICENSE_REGISTRY.json, then `ollama pull <model>`.")
    if by_id["codex_exec"].status != report_generator.PASS:
        steps.append("Install the Codex CLI and log in with the existing ChatGPT "
                     "subscription (HUMAN_GATE), then re-run selftest. Until then code "
                     "review falls back to local model + Claude.")
    if by_id["engine_validate"].status != report_generator.PASS:
        steps.append("Install the engine locally (Godot 4.3 for this repository) or set "
                     "GODOT_BIN so headless validation can run every commit.")
    if by_id["android_build"].status != report_generator.PASS:
        steps.append("Create the Android export preset + debug keystore once in the "
                     "editor and install export templates (HUMAN_GATE), then re-run "
                     "`main.py engine build`.")
    if by_id["blender_background"].status != report_generator.PASS:
        steps.append("Install Blender if 3D asset processing is needed; the 2D Godot "
                     "pipeline does not require it.")
    steps.append("Infrastructure gate (section 41 STEP 18): create "
                 "GAME_10_MASTER_PLAN.md only after the checks above are PASS on the "
                 "development PC.")
    return steps


# ---------------------------------------------------------------- status
def cmd_status(args: argparse.Namespace) -> int:
    sm = state_manager.StateManager()
    queue = task_queue.TaskQueue()
    _print_json({
        "state": sm.summary(),
        "queue_counts": queue.counts(),
        "artifact_verification": sm.verify_against_disk(),
        "next_queued": [t.task_id for t in queue.list(status="QUEUED", limit=10)],
    })
    return 0


# ---------------------------------------------------------------- engine
def cmd_engine(args: argparse.Namespace) -> int:
    policy = Policy.load()
    engine = engine_runner.EngineRunner(policy, engine=args.engine)
    if args.engine_action == "caps":
        _print_json(engine.capabilities())
        return 0
    if args.engine_action == "validate":
        result = engine.validate()
        _print_json(result)
        state_manager.StateManager().update(engine_status=result["status"])
        return 0 if result["status"] == "OK" else 1
    out = Path(args.out) if args.out else paths.BUILDS_DIR / "manual" / "game.apk"
    if not out.is_absolute():
        out = paths.ROOT / out
    result = engine.build_android(out)
    _print_json(result)
    sm = state_manager.StateManager()
    sm.update(build_status=result["status"])
    if result["status"] == "OK":
        sm.register_artifact("last_apk", out)
    return 0 if result["status"] == "OK" else 1


# ------------------------------------------------------------------ task
def cmd_task(args: argparse.Namespace) -> int:
    queue = task_queue.TaskQueue()
    if args.task_action == "list":
        rows = queue.list(status=args.status, game_id=args.game)
        _print_json([{"task_id": t.task_id, "status": t.status, "phase": t.phase,
                      "agent": t.agent, "priority": t.priority, "goal": t.goal[:100],
                      "retry": f"{t.retry_count}/{t.max_retry}"} for t in rows])
        return 0
    if args.task_action == "show":
        task = queue.get(args.task_id)
        if task is None:
            print(f"no such task: {args.task_id}", file=sys.stderr)
            return 1
        _print_json({"task": task.to_dict(), "history": queue.history(args.task_id)})
        return 0
    # add
    router = AgentRouter(Policy.load())
    plan = router.route(args.kind)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    task_id = args.task_id or f"{args.game or 'COMPANY'}_{args.kind}_{stamp}"
    task = queue.enqueue(task_queue.Task(
        task_id=task_id, goal=args.goal, game_id=args.game, phase=args.phase,
        department=args.kind, agent=plan.selected, priority=args.priority,
        acceptance_criteria=args.criteria or [],
        max_retry=int(Policy.load().get("max_retry", 5)),
        reviewer=plan.reviewer))
    _print_json({"enqueued": task.task_id, "routing": plan.to_dict()})
    return 0


# ---------------------------------------------------------------- resume
def cmd_resume(args: argparse.Namespace) -> int:
    """Section 15: reconcile state with disk, then requeue interrupted work."""
    sm = state_manager.StateManager()
    queue = task_queue.TaskQueue()
    verification = sm.verify_against_disk()
    requeued: list[str] = []
    for task in queue.list(status="RUNNING"):
        queue.set_status(task.task_id, "QUEUED", note="requeued on resume")
        requeued.append(task.task_id)
    sm.record_event("resume", requeued=requeued,
                    problems=len(verification["problems"]))
    _print_json({
        "verification": verification,
        "requeued_running_tasks": requeued,
        "queue_counts": queue.counts(),
        "state": sm.summary(),
    })
    return 0


# --------------------------------------------------------------- license
def cmd_license(args: argparse.Namespace) -> int:
    lm = LicenseManager()
    if args.license_action == "list":
        _print_json(lm.all())
        return 0
    gate = lm.release_gate(args.ids or [e["id"] for e in lm.all()])
    _print_json(gate)
    return 0 if gate["release_allowed"] else 1


# ------------------------------------------------------------------ main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="company.orchestrator.main",
        description="AI_GAME_COMPANY local orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="detect hardware, tools and CLI capabilities")

    p_init = sub.add_parser("init", help="create runtime files and initial state")
    p_init.add_argument("--force", action="store_true", help="reset company_state.json")

    sub.add_parser("selftest", help="run the section 40 checklist and write the report")
    sub.add_parser("status", help="print state, queue counts and artifact verification")
    sub.add_parser("resume", help="verify state against disk and requeue interrupted tasks")

    p_engine = sub.add_parser("engine", help="engine validate / build / caps")
    p_engine.add_argument("engine_action", choices=["validate", "build", "caps"])
    p_engine.add_argument("--engine", choices=["godot", "unity"], default=None)
    p_engine.add_argument("--out", default=None, help="output APK path for build")

    p_task = sub.add_parser("task", help="task queue operations")
    p_task.add_argument("task_action", choices=["add", "list", "show"])
    p_task.add_argument("--task-id", default=None)
    p_task.add_argument("--goal", default="")
    p_task.add_argument("--kind", default="json_config")
    p_task.add_argument("--game", default=None)
    p_task.add_argument("--phase", default=None)
    p_task.add_argument("--priority", type=int, default=100)
    p_task.add_argument("--status", default=None)
    p_task.add_argument("--criteria", nargs="*", default=None)

    p_license = sub.add_parser("license", help="license registry operations")
    p_license.add_argument("license_action", choices=["list", "gate"])
    p_license.add_argument("--ids", nargs="*", default=None)

    return parser


HANDLERS = {
    "doctor": cmd_doctor, "init": cmd_init, "selftest": cmd_selftest,
    "status": cmd_status, "engine": cmd_engine, "task": cmd_task,
    "resume": cmd_resume, "license": cmd_license,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "task" and args.task_action == "add" and not args.goal:
        print("task add requires --goal", file=sys.stderr)
        return 2
    if args.command == "task" and args.task_action == "show" and not args.task_id:
        print("task show requires --task-id", file=sys.stderr)
        return 2
    return HANDLERS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
