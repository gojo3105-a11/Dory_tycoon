"""Filesystem layout for AI_GAME_COMPANY (master prompt section 12).

Every other module resolves paths through here so nothing hardcodes an
absolute path and the whole tree can be relocated or symlinked.
"""
from __future__ import annotations

import os
from pathlib import Path


def company_root() -> Path:
    """Root of the AI_GAME_COMPANY tree."""
    override = os.environ.get("AI_GAME_COMPANY_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    # <root>/company/orchestrator/paths.py -> parents[2] == <root>
    return Path(__file__).resolve().parents[2]


ROOT = company_root()

CONFIG_DIR = ROOT / "config"
POLICY_FILE = CONFIG_DIR / "company_policy.json"
MODEL_REGISTRY_FILE = CONFIG_DIR / "model_registry.json"
ENGINES_FILE = CONFIG_DIR / "engines.json"

COMPANY_DIR = ROOT / "company"
STATE_DIR = COMPANY_DIR / "state"
QUEUE_DIR = COMPANY_DIR / "queue"
PROMPTS_DIR = COMPANY_DIR / "prompts"
VALIDATORS_DIR = COMPANY_DIR / "validators"
AGENTS_DIR = COMPANY_DIR / "agents"

STATE_FILE = STATE_DIR / "company_state.json"
HARDWARE_PROFILE_FILE = STATE_DIR / "HARDWARE_PROFILE.json"
TASK_DB_FILE = QUEUE_DIR / "tasks.sqlite3"
AI_OUTPUT_DIR = STATE_DIR / "ai_outputs"
RETRY_DIR = STATE_DIR / "retry"

TOOLS_DIR = ROOT / "tools"
BLENDER_TOOLS_DIR = TOOLS_DIR / "blender"
ANDROID_TOOLS_DIR = TOOLS_DIR / "android"

SHARED_ASSETS_DIR = ROOT / "shared_assets"
GAMES_DIR = ROOT / "games"
BUILDS_DIR = ROOT / "builds"
REPORTS_DIR = ROOT / "reports"
LOGS_DIR = ROOT / "logs"
TESTS_DIR = ROOT / "tests"
WORKFLOWS_DIR = ROOT / "workflows"
LICENSES_DIR = ROOT / "licenses"
LICENSE_REGISTRY_FILE = LICENSES_DIR / "LICENSE_REGISTRY.json"

SETUP_REPORT_FILE = ROOT / "AI_COMPANY_SETUP_REPORT.md"

# The game project this company currently operates on. The master prompt
# assumes Unity; this repository is a Godot 4.3 project one level up.
def target_project_root() -> Path:
    override = os.environ.get("AI_GAME_COMPANY_PROJECT")
    if override:
        return Path(override).expanduser().resolve()
    return ROOT.parent


RUNTIME_DIRS = (
    STATE_DIR, QUEUE_DIR, AI_OUTPUT_DIR, RETRY_DIR,
    LOGS_DIR, REPORTS_DIR, BUILDS_DIR, GAMES_DIR, LICENSES_DIR,
)


def ensure_dirs() -> None:
    for d in RUNTIME_DIRS:
        d.mkdir(parents=True, exist_ok=True)


def rel(p: Path | str) -> str:
    """Path relative to the company root, for readable reports."""
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except (ValueError, OSError):
        return str(p)
