"""Orchestrator CLI.

    python -m company.orchestrator.main doctor    what this machine can run
    python -m company.orchestrator.main status    state + queue, reconciled

Master prompt section 36: CLI status output first, dashboards later. Section
13: Claude Code is not the repeating execution loop - this is, so it must be
runnable and inspectable without Claude present.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow running as a script from anywhere in the repo, not just as a module.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from company.orchestrator.codex_runner import (  # noqa: E402
    CodexLimited, CodexRunner, CodexUnavailable, ReviewNotRun,
)
from company.orchestrator.hardware import HardwareProfile  # noqa: E402
from company.orchestrator.ollama_client import (  # noqa: E402
    ModelDoesNotFit, ModelNotApproved, ModelNotInstalled,
    NonLocalEndpointRefused, OllamaClient, OllamaUnavailable,
)
from company.orchestrator.policy import Policy  # noqa: E402
from company.orchestrator.report_generator import (  # noqa: E402
    GameNarrative, MissingRequiredSection, ReportGenerator, WouldDowngradeReport,
)
from company.orchestrator.state import CompanyState  # noqa: E402
from company.orchestrator.tasks import TaskQueue  # noqa: E402
from company.orchestrator.teamwork import (  # noqa: E402
    NotCodexOwned, TaskBoard, TaskNotFound, build_prompt, run_task,
)
from company.orchestrator.unity_runner import UnityRunner  # noqa: E402

COMPANY_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = COMPANY_ROOT.parent
CONFIG_DIR = COMPANY_ROOT / "config"
STATE_PATH = COMPANY_ROOT / "company" / "state" / "company_state.json"
QUEUE_PATH = COMPANY_ROOT / "company" / "queue" / "tasks.db"

STATUS_MARK = {
    "VIABLE": "[ OK ]", "LIMITED": "[LTD ]",
    "NOT_VIABLE": "[FAIL]", "UNKNOWN": "[ ?? ]",
}


def _codex_binary() -> str:
    """The codex path to launch, preferring the one detect-environment recorded.

    Not just "codex": on Windows npm's extension-less shim is unlaunchable by
    subprocess, which is what produced `codex --version could not run:
    [WinError 2]` on the build PC even though codex was installed and on PATH.
    """
    return CodexRunner.resolve_binary(CONFIG_DIR / "HARDWARE_PROFILE.json")


def _load_policy() -> Policy:
    path = CONFIG_DIR / "company_policy.json"
    if not path.exists():
        print(f"WARNING: no policy at {path} - treating everything as denied.")
        return Policy.deny_all()
    return Policy.load(path)


def cmd_doctor(_args: argparse.Namespace) -> int:
    policy = _load_policy()

    print("=== POLICY ===")
    for key in ("allow_paid_api", "allow_paid_assets", "allow_cloud_ai_generation",
                "allow_auto_purchase", "use_local_ai", "ollama_local_only"):
        print(f"  {key:32} {policy.allows(key)}")

    present = policy.check_env_for_paid_keys(dict(os.environ))
    if present:
        # Section 7: presence is not permission. Naming them proves the guard
        # saw them and chose not to use them.
        print(f"  paid API keys present but BLOCKED by policy: {', '.join(present)}")
    else:
        print("  no blocked API keys present in the environment")

    profile_path = CONFIG_DIR / "HARDWARE_PROFILE.json"
    if not profile_path.exists():
        print("\n=== HARDWARE ===")
        print("  No HARDWARE_PROFILE.json.")
        print("  Run AI_GAME_COMPANY/tools/detect-environment.ps1 on the PC first.")
        print("  Section 38: nothing is assumed to be installed without evidence.")
        return 1

    profile = HardwareProfile.load(profile_path)
    print("\n=== HARDWARE ===")
    print(f"  CPU  {profile.cpu}")
    print(f"  RAM  {profile.ram_total_gb:.1f} GB total / {profile.ram_free_gb:.1f} GB free")
    print(f"  GPU  {', '.join(profile.gpu_names) or 'none'}"
          f"{'' if profile.has_dedicated_gpu else '  (no dedicated GPU / no CUDA)'}")

    tier, why = profile.recommend_llm_tier()
    print(f"\n  local model tier: {tier or 'NONE'}")
    print(f"    {why}")

    print("\n=== CAPABILITIES ===")
    exit_code = 0
    for verdict in profile.verdicts():
        mark = STATUS_MARK.get(verdict.status, "[ ?? ]")
        print(f"  {mark} {verdict.capability}")
        print(f"         {verdict.reason}")
        if verdict.recommendation:
            print(f"         -> {verdict.recommendation}")
        if verdict.status == "NOT_VIABLE" and verdict.capability == "unity_android_build":
            exit_code = 1

    return exit_code


def cmd_ollama(args: argparse.Namespace) -> int:
    """Is the local model gateway usable, and is any installed model allowed?

    Three separate questions that are easy to conflate: reachable, licensed
    (section 8), and small enough to actually load on this machine (section 5).
    A model can pass the first two and still be unusable.
    """
    policy = _load_policy()
    registry = CONFIG_DIR / "LICENSE_REGISTRY.json"

    try:
        client = OllamaClient(
            local_only=policy.allows("ollama_local_only"),
            registry_path=registry if registry.is_file() else None,
            state_path=STATE_PATH,
        )
    except NonLocalEndpointRefused as exc:
        print(f"REFUSED: {exc}")
        return 2

    profile_path = CONFIG_DIR / "HARDWARE_PROFILE.json"
    if not profile_path.exists():
        print("REFUSED: RAM fit check failed: no HARDWARE_PROFILE.json, so model "
              "sizes cannot be checked against this machine's RAM.")
        return 2

    profile = HardwareProfile.load(profile_path)

    if getattr(args, "use", None):
        try:
            client.use_model(args.use, profile)
        except (ModelNotInstalled, ModelNotApproved, ModelDoesNotFit,
                OllamaUnavailable) as exc:
            print(f"REFUSED: {exc}")
            return 2
        print(f"Active Ollama model set to {args.use}")
        return 0

    try:
        models = client.list_models()
    except OllamaUnavailable as exc:
        print(f"ERROR: installation check failed: {exc}")
        return 1

    print("=== OLLAMA MODELS ===")
    if not models:
        print("  no models installed")
        return 0

    approved = client.approved_models()
    active = client.active_model()
    recorded_sizes = dict(profile.ollama_model_sizes)
    for model in models:
        size_gb = recorded_sizes.get(model.name, model.size_gb)
        fit, _why = profile.model_fit(size_gb)
        licence = "APPROVED" if model.name in approved else "NOT APPROVED"
        selected = "ACTIVE" if model.name == active else "inactive"
        print(f"  {model.name}  licence={licence}  RAM={fit}  active={selected}")
    return 0


def cmd_codex(args: argparse.Namespace) -> int:
    """Is the independent reviewer usable? Section 3.

    Deliberately does not decide whether Codex is signed in: ~/.codex/auth.json
    is on the policy's secrets_never_touched list, and initial_codex_login is a
    HUMAN_GATE. --doctor shows the CLI's own answer instead.
    """
    policy = _load_policy()
    runner = CodexRunner(repo_root=REPO_ROOT, policy=policy, binary=_codex_binary())

    print("=== CODEX ===")
    print(f"  binary: {runner.binary}")
    print(runner.status_summary())

    if not args.doctor:
        print("\n  run with --doctor for the CLI's own auth/config diagnosis")
        return 0

    print("\n=== codex doctor (raw, not interpreted) ===")
    try:
        result = runner.doctor()
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        print(f"  could not run: {exc}")
        return 1
    print(result.stdout or result.stderr or "  (no output)")
    return 0 if result.ok else 1


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Write Reports/dashboard.html - which AI can work, and what blocks the rest.

    Reads committed files only, so it produces the same answer on the build PC
    and in a container that has never seen Unity. It prints what it could NOT
    read, because a blank section on that page means "no evidence", and
    someone skimming it would otherwise read blank as fine.
    """
    from company.orchestrator import dashboard as dash

    snapshot = dash.collect(REPO_ROOT)
    path = dash.write(REPO_ROOT)

    print(f"Wrote {path}")
    counts = {state: sum(1 for a in snapshot.agents if a.state == state)
              for state in (dash.READY, dash.GATED, dash.BLOCKED, dash.UNKNOWN)}
    print(f"  {counts[dash.READY]} ready, {counts[dash.GATED]} gated, "
          f"{counts[dash.BLOCKED]} blocked, {counts[dash.UNKNOWN]} unknown")

    if snapshot.missing:
        print("\n  could not read (those sections show as 'no evidence', not as OK):")
        for name in snapshot.missing:
            print(f"    - {name}")

    if args.open:
        import webbrowser
        webbrowser.open(path.as_uri())
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Open the control panel: the dashboard plus buttons that actually run.

    Only useful on the machine that has the AI tooling. Bound to loopback and
    token-guarded - see server.py for why both are needed rather than one.
    """
    from company.orchestrator.server import serve

    return serve(REPO_ROOT, COMPANY_ROOT, port=args.port)


def _board() -> TaskBoard:
    return TaskBoard.load(CONFIG_DIR / "TASKBOARD.json")


def cmd_team(args: argparse.Namespace) -> int:
    """The shared board Claude and Codex both work from.

    `team board` is readable without Codex installed or signed in - the split
    of work is useful information on its own, and printing it must not depend
    on the CLI being available.
    """
    board = _board()

    if not board.tasks:
        print(f"No tasks on {board.path}.")
        return 1

    if args.action == "board":
        by_owner: dict[str, list] = {}
        for task in board.tasks:
            by_owner.setdefault(task.owner, []).append(task)

        print("=== SHARED TASK BOARD ===")
        print(f"  {board.path}\n")
        for owner in sorted(by_owner):
            print(f"  {owner.upper()}")
            for task in by_owner[owner]:
                unmet = board.unmet_dependencies(task)
                blocked = f"  waiting on {', '.join(unmet)}" if unmet else ""
                print(f"    [{task.status:11}] {task.id:10} {task.title}{blocked}")
            print()
        return 0

    # Everything below actually invokes Codex.
    if not args.task:
        print("ERROR: 'team run' needs --task <id>. Run 'team board' to see the ids.")
        return 2

    policy = _load_policy()
    codex = CodexRunner(repo_root=REPO_ROOT, policy=policy, model=args.model,
                        binary=_codex_binary())

    if not policy.allows("allow_codex_write"):
        print("REFUSED: policy allow_codex_write is not true.")
        print("  Codex can review but not write. Section 7: the gate is the code, not the prose.")
        return 3

    try:
        task = board.get(args.task)
    except TaskNotFound as exc:
        print(f"ERROR: {exc}")
        return 2

    print(f"=== HANDING {task.id} TO CODEX ===")
    print(f"  {task.title}")
    print(f"  allowlist: {', '.join(task.files) or '(none)'}")

    if args.dry_run:
        print("\n--- prompt (not sent) ---")
        print(build_prompt(task, board))
        return 0

    print("  running codex exec --sandbox workspace-write ...\n")

    try:
        run = run_task(board, args.task, codex, REPO_ROOT,
                       timeout_seconds=args.timeout)
    except NotCodexOwned as exc:
        print(f"REFUSED: {exc}")
        return 2
    except CodexLimited as exc:
        # Section 3: degrade, never spend. This is a distinct exit code so a
        # wrapper can tell "out of quota" from "the run went wrong".
        print(f"CODEX_LIMITED: {exc}")
        return 4
    except (CodexUnavailable, ReviewNotRun) as exc:
        print(f"FAILED: {exc}")
        return 1

    print("--- codex said ---")
    print(run.summary)

    print("\n--- files this run changed ---")
    for path in run.changed:
        print(f"  {path}")
    if not run.changed:
        print("  (none)")

    if run.outside_allowlist:
        print("\nBLOCKED - these are outside the task's allowlist:")
        for path in run.outside_allowlist:
            print(f"  {path}")
        print("\n  Nothing was reverted: the working tree may hold work in")
        print("  progress from the other agent, and discarding that silently")
        print("  would be worse than the overreach. Review them by hand.")
        return 1

    if not run.ok:
        print("\nBLOCKED - the run changed nothing. That is not progress.")
        return 1

    print(f"\n  status -> {run.task.status} (NOT done: nothing here compiled the project)")
    print(f"  next: python -m company.orchestrator.main build --game {args.game}")
    print("  then review the diff and commit it yourself - this never commits.")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    state = CompanyState.load(STATE_PATH)

    # Section 15: a state file is a claim. Check it before printing it.
    discrepancies = state.verify_against_disk(REPO_ROOT)
    if discrepancies:
        print("=== STATE CORRECTED AGAINST DISK ===")
        for item in discrepancies:
            print(f"  {item.field_name}")
            print(f"    claimed: {item.claimed}")
            print(f"    actual : {item.actual}")
            print(f"    action : {item.action_taken}")
        state.save()
        print()

    print("=== STATE ===")
    for key in ("current_game", "current_phase", "build_status", "qa_status",
                "codex_status", "ollama_status", "last_successful_commit"):
        print(f"  {key:24} {state.data.get(key)}")

    games = state.data.get("games") or {}
    if games:
        print("\n=== GAMES ===")
        for game_id, game in sorted(games.items()):
            apk = CompanyState._find_apk(REPO_ROOT, game_id)
            print(f"  {game_id:10} phase={game.get('phase')}  apk={apk.name if apk else 'NONE'}")

    queue = TaskQueue(QUEUE_PATH)
    try:
        counts = queue.counts()
        print("\n=== QUEUE ===")
        if not counts:
            print("  empty")
        for status, count in sorted(counts.items()):
            print(f"  {status:20} {count}")

        stuck = queue.blocked()
        if stuck:
            print("\n=== NEEDS ATTENTION ===")
            for row in stuck:
                print(f"  [{row['status']}] {row['task_id']}: {row['goal']}")
                if row["last_error"]:
                    print(f"      {row['last_error']}")
    finally:
        queue.close()

    return 0


def cmd_build(args: argparse.Namespace) -> int:
    """Run generate -> validate -> build locally, bypassing GitHub Actions.

    The self-hosted runner is one way to reach Unity, not the only one. When it
    is down, this drives the same wait-for-unity.ps1 invocations the working
    workflow uses, on the same machine, so a broken runner stops being a reason
    to have no APK.
    """
    policy = _load_policy()

    unity_path = args.unity_path or UnityRunner.unity_path_from_profile(
        CONFIG_DIR / "HARDWARE_PROFILE.json"
    )
    if not unity_path:
        print("ERROR: no Unity editor path.")
        print("  Run AI_GAME_COMPANY/tools/detect-environment.ps1, or pass --unity-path.")
        print("  Section 38: the editor is not assumed to be anywhere without evidence.")
        return 2

    print(f"=== LOCAL BUILD: {args.game} ===")
    print(f"  Unity: {unity_path}")
    print("  This takes a while - Gradle on a cold cache is the slow part.\n")

    runner = UnityRunner(repo_root=REPO_ROOT, policy=policy, unity_path=unity_path)
    results, apk = runner.run_pipeline(args.game)

    for result in results:
        mark = "[ OK ]" if result.ok else "[FAIL]"
        print(f"  {mark} {result.step:9} exit={result.exit_code}")
        if result.log_path:
            print(f"         log: {result.log_path}")
        if result.detail:
            print(f"         {result.detail}")
        if not result.ok and result.stderr.strip():
            print(f"         stderr: {result.stderr.strip()[:400]}")

    # Section 18/32: exit code AND build report AND a real file on disk. The
    # pipeline already applied all three; this only reports which way it went.
    if apk is None:
        print("\nBUILD_FAILED - no verified APK.")
        print("  Section 38: this is not reported as a success.")
        return 1

    print(f"\nAPK: {apk}")
    print(f"  size: {apk.stat().st_size / (1024 * 1024):.2f} MB")
    print("\nNext: run scripts/dev/report-build-status.ps1 -Commit so this is "
          "readable from the repository.")
    return 0


def _narrative_path(game_id: str) -> Path:
    return COMPANY_ROOT / "games" / game_id / "narrative.json"


def _load_narrative(game_id: str) -> GameNarrative:
    path = _narrative_path(game_id)
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. The report's narrative sections (how it plays, what "
            "makes it different, controls) cannot be derived from the filesystem - "
            "they have to be written."
        )
    import json
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    known = {f for f in GameNarrative.__dataclass_fields__}
    return GameNarrative(**{k: v for k, v in data.items() if k in known})


def cmd_gate(args: argparse.Namespace) -> int:
    """Section 23: may this game be called COMPLETE, and may the next one start?"""
    generator = ReportGenerator(REPO_ROOT)
    ok, blockers = generator.is_complete(args.game)

    print(f"=== COMPLETION GATE: {args.game} ===")
    if ok:
        print("  COMPLETE - all checks pass. The next game may start.")
        return 0

    print("  NOT COMPLETE. Blockers:")
    for blocker in blockers:
        print(f"    - {blocker}")
    print("\n  Section 23: do not start the next game until these clear.")
    return 1


def cmd_report(args: argparse.Namespace) -> int:
    generator = ReportGenerator(REPO_ROOT)
    try:
        narrative = _load_narrative(args.game)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 2

    try:
        path = generator.write(args.game, narrative, force=args.force)
    except MissingRequiredSection as exc:
        print(f"ERROR: {exc}")
        return 2
    except WouldDowngradeReport as exc:
        print(f"REFUSED: {exc}")
        return 3

    print(f"Wrote {path}")
    ok, blockers = generator.is_complete(args.game)
    if not ok:
        # The report is still written - it just says what is missing, which is
        # the point. Section 38: do not paper over an incomplete build.
        print("Note: this game is NOT complete yet:")
        for blocker in blockers:
            print(f"  - {blocker}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="what this machine can actually run").set_defaults(func=cmd_doctor)
    sub.add_parser("status", help="state and queue, reconciled with disk").set_defaults(func=cmd_status)
    ollama = sub.add_parser(
        "ollama", help="list or select local models after licence and RAM checks"
    )
    ollama_actions = ollama.add_mutually_exclusive_group()
    ollama_actions.add_argument("--list", action="store_true",
                                help="list installed models (the default)")
    ollama_actions.add_argument("--use", metavar="MODEL",
                                help="persist the active installed, approved model")
    ollama.set_defaults(func=cmd_ollama)

    codex = sub.add_parser("codex", help="independent reviewer: available, policy, login gate")
    codex.add_argument("--doctor", action="store_true",
                       help="also run 'codex doctor' and print its raw output")
    codex.set_defaults(func=cmd_codex)

    serve_cmd = sub.add_parser("serve", help="open the control panel in a browser (this PC only)")
    serve_cmd.add_argument("--port", type=int, default=8765)
    serve_cmd.set_defaults(func=cmd_serve)

    dashboard = sub.add_parser("dashboard", help="write Reports/dashboard.html")
    dashboard.add_argument("--open", action="store_true",
                           help="open it in the default browser afterwards")
    dashboard.set_defaults(func=cmd_dashboard)

    team = sub.add_parser("team", help="the shared board Claude and Codex both work from")
    team.add_argument("action", choices=["board", "run"],
                      help="board: print who is doing what. run: hand a task to Codex")
    team.add_argument("--task", default=None, help="task id, for 'run'")
    team.add_argument("--game", default="game01",
                      help="game id used in the follow-up build suggestion")
    team.add_argument("--model", default=None, help="override the Codex model")
    team.add_argument("--timeout", type=int, default=1800,
                      help="seconds before the Codex run is abandoned (default 1800)")
    team.add_argument("--dry-run", action="store_true",
                      help="print the prompt that would be sent and stop")
    team.set_defaults(func=cmd_team)

    build = sub.add_parser("build", help="run generate/validate/build locally, no CI")
    build.add_argument("--game", default="game01")
    build.add_argument("--unity-path", default=None,
                       help="Unity.exe path; defaults to the one in HARDWARE_PROFILE.json")
    build.set_defaults(func=cmd_build)

    gate = sub.add_parser("gate", help="may this game be called COMPLETE?")
    gate.add_argument("--game", default="game01")
    gate.set_defaults(func=cmd_gate)

    report = sub.add_parser("report", help="write Reports/GameXX_Report.txt")
    report.add_argument("--game", default="game01")
    report.add_argument("--force", action="store_true",
                        help="overwrite even if that would replace a report "
                             "recording an APK this machine cannot see")
    report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
