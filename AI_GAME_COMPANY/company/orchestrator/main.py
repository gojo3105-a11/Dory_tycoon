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

from company.orchestrator.codex_runner import CodexRunner  # noqa: E402
from company.orchestrator.hardware import HardwareProfile  # noqa: E402
from company.orchestrator.ollama_client import (  # noqa: E402
    NonLocalEndpointRefused, OllamaClient,
)
from company.orchestrator.policy import Policy  # noqa: E402
from company.orchestrator.report_generator import (  # noqa: E402
    GameNarrative, MissingRequiredSection, ReportGenerator, WouldDowngradeReport,
)
from company.orchestrator.state import CompanyState  # noqa: E402
from company.orchestrator.tasks import TaskQueue  # noqa: E402

COMPANY_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = COMPANY_ROOT.parent
CONFIG_DIR = COMPANY_ROOT / "config"
STATE_PATH = COMPANY_ROOT / "company" / "state" / "company_state.json"
QUEUE_PATH = COMPANY_ROOT / "company" / "queue" / "tasks.db"

STATUS_MARK = {
    "VIABLE": "[ OK ]", "LIMITED": "[LTD ]",
    "NOT_VIABLE": "[FAIL]", "UNKNOWN": "[ ?? ]",
}


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


def cmd_ollama(_args: argparse.Namespace) -> int:
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
        )
    except NonLocalEndpointRefused as exc:
        print(f"REFUSED: {exc}")
        return 2

    print("=== OLLAMA ===")
    print(client.status_summary())

    profile_path = CONFIG_DIR / "HARDWARE_PROFILE.json"
    if not profile_path.exists():
        print("\nNo HARDWARE_PROFILE.json, so model sizes cannot be checked "
              "against this machine's RAM.")
        return 0

    profile = HardwareProfile.load(profile_path)
    print(f"\n=== FITS IN RAM? ({profile.ram_total_gb:.1f} GB total, "
          f"{profile.ram_free_gb:.1f} GB free) ===")

    sizes = profile.ollama_model_sizes
    if not sizes:
        print("  no models recorded in the hardware profile")
        return 0

    exit_code = 0
    for name, size_gb in sizes:
        fit, why = profile.model_fit(size_gb)
        print(f"  {STATUS_MARK.get(fit, '[ ?? ]')} {name}")
        print(f"         {why}")
        if fit == "NOT_VIABLE":
            exit_code = 1

    tier, tier_why = profile.recommend_llm_tier()
    print(f"\n  what fits instead: {tier or 'NONE'}")
    print(f"    {tier_why}")
    return exit_code


def cmd_codex(args: argparse.Namespace) -> int:
    """Is the independent reviewer usable? Section 3.

    Deliberately does not decide whether Codex is signed in: ~/.codex/auth.json
    is on the policy's secrets_never_touched list, and initial_codex_login is a
    HUMAN_GATE. --doctor shows the CLI's own answer instead.
    """
    policy = _load_policy()
    runner = CodexRunner(repo_root=REPO_ROOT, policy=policy)

    print("=== CODEX ===")
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
    sub.add_parser("ollama", help="local model gateway: reachable, licensed, fits in RAM"
                   ).set_defaults(func=cmd_ollama)

    codex = sub.add_parser("codex", help="independent reviewer: available, policy, login gate")
    codex.add_argument("--doctor", action="store_true",
                       help="also run 'codex doctor' and print its raw output")
    codex.set_defaults(func=cmd_codex)

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
