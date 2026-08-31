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

from company.orchestrator.hardware import HardwareProfile  # noqa: E402
from company.orchestrator.policy import Policy  # noqa: E402
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="what this machine can actually run").set_defaults(func=cmd_doctor)
    sub.add_parser("status", help="state and queue, reconciled with disk").set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
