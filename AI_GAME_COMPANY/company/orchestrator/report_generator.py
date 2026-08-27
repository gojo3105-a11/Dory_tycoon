"""Report writers (master prompt sections 33, 34, 40, 43).

Every check records EXPECTED / ACTUAL / STATUS / LOG_PATH / OUTPUT_PATH, and
the status vocabulary is the master prompt's: PASS / FAIL / LIMITED /
HUMAN_GATE / BLOCKED / SKIPPED.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths

PASS, FAIL, LIMITED = "PASS", "FAIL", "LIMITED"
HUMAN_GATE, BLOCKED, SKIPPED = "HUMAN_GATE", "BLOCKED", "SKIPPED"

_ICON = {PASS: "PASS", FAIL: "FAIL", LIMITED: "LIMITED",
         HUMAN_GATE: "HUMAN_GATE", BLOCKED: "BLOCKED", SKIPPED: "SKIPPED"}


@dataclass
class CheckResult:
    """One row of the section 40 completion checklist."""
    id: str
    name: str
    expected: str
    actual: str
    status: str
    log_path: str | None = None
    output_path: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    duration_s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def blocking(self) -> bool:
        """Only FAIL blocks; LIMITED and HUMAN_GATE are honest, non-fatal."""
        return self.status == FAIL


def _fmt(value: str | None) -> str:
    return f"`{value}`" if value else "-"


def render_setup_report(checks: list[CheckResult], *,
                        hardware: dict[str, Any],
                        policy_summary: dict[str, Any],
                        state_summary: dict[str, Any],
                        environment_note: str,
                        findings: list[str] | None = None,
                        next_steps: list[str] | None = None) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    counts: dict[str, int] = {}
    for c in checks:
        counts[c.status] = counts.get(c.status, 0) + 1
    verdict = ("BLOCKED - a required check failed" if any(c.blocking for c in checks)
               else "INFRASTRUCTURE READY (with limits recorded below)")

    lines: list[str] = [
        "# AI_COMPANY_SETUP_REPORT",
        "",
        f"- Generated: {generated}",
        f"- Verdict: **{verdict}**",
        "- Result counts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
        "",
        "> Status vocabulary (master prompt sections 14, 43): **PASS** verified by a real",
        "> command or file; **LIMITED** the component is not installed or reachable here,",
        "> the adapter is implemented and degrades cleanly; **HUMAN_GATE** a person must",
        "> act (login, licence, signing key, device approval); **FAIL** blocking defect.",
        "",
        "## 0. Environment this run measured",
        "",
        environment_note,
        "",
        "## 1. Completion checklist (master prompt section 40)",
        "",
        "| # | Check | EXPECTED | ACTUAL | STATUS | LOG_PATH | OUTPUT_PATH |",
        "|---|-------|----------|--------|--------|----------|-------------|",
    ]
    for i, c in enumerate(checks, 1):
        lines.append(
            f"| {i} | {c.name} | {c.expected} | {c.actual} | "
            f"**{_ICON.get(c.status, c.status)}** | {_fmt(c.log_path)} | {_fmt(c.output_path)} |")

    lines += ["", "## 2. Hardware profile (section 6)", "", "```json",
              json.dumps(hardware, indent=2, ensure_ascii=False), "```", ""]
    lines += ["## 3. Cost policy (section 7)", "", "```json",
              json.dumps(policy_summary, indent=2, ensure_ascii=False), "```", ""]
    lines += ["## 4. Company state (section 15)", "", "```json",
              json.dumps(state_summary, indent=2, ensure_ascii=False), "```", ""]

    if findings:
        lines += ["## 5. QA findings from this run", ""]
        lines += [f"- {f}" for f in findings]
        lines.append("")
    if next_steps:
        lines += ["## 6. Next steps", ""]
        lines += [f"{i}. {s}" for i, s in enumerate(next_steps, 1)]
        lines.append("")
    return "\n".join(lines)


def write_setup_report(checks: list[CheckResult], **kwargs: Any) -> Path:
    paths.SETUP_REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    paths.SETUP_REPORT_FILE.write_text(render_setup_report(checks, **kwargs),
                                       encoding="utf-8")
    json_path = paths.REPORTS_DIR / "setup_checks.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps([c.to_dict() for c in checks], indent=2,
                                    ensure_ascii=False), encoding="utf-8")
    return paths.SETUP_REPORT_FILE


GAME_REPORT_TEMPLATE = """게임 번호: {game_id}
게임 이름: {game_name}
게임 종류: {genre}

[게임 방법]
{how_to_play}

[게임 특징]
{features}

[조작 방법]
{controls}

[게임 목표]
{goal}

[성장 요소]
{progression}

[캐릭터]
공통 캐릭터 사용: {common_character}
의상: {costume}
장비: {equipment}
Character Route: {character_route}

[맵]
{map_description}

[사용 AI]
Claude Code: {ai_claude}
Codex: {ai_codex}
Local LLM: {ai_local}
Image AI: {ai_image}
3D AI: {ai_3d}

[Asset]
주요 Asset: {assets}
License Status: {license_status}

[QA]
Compile: {qa_compile}
Gameplay: {qa_gameplay}
Android Build: {qa_build}

[APK]
파일명: {apk_name}
Package Name: {apk_package}
Version: {apk_version}
파일 존재 여부: {apk_exists}

[알려진 문제]
{known_issues}

[다음 버전 개선사항]
{next_version}
"""

_REQUIRED_GAME_FIELDS = ("game_id", "game_name", "genre", "how_to_play", "features")


def write_game_report(data: dict[str, Any]) -> Path:
    """Section 33. Minimum required: 게임 종류 / 게임 방법 / 게임 특징."""
    missing = [f for f in _REQUIRED_GAME_FIELDS if not data.get(f)]
    if missing:
        raise ValueError(f"game report missing required fields: {missing}")
    filled = {k: data.get(k, "(미정)") for k in
              set(_field_names(GAME_REPORT_TEMPLATE)) | set(data)}
    filled.update(data)
    paths.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = paths.REPORTS_DIR / f"{data['game_id']}_Report.txt"
    path.write_text(GAME_REPORT_TEMPLATE.format(**filled), encoding="utf-8")
    return path


def write_ai_activity_report(game_id: str, activity: dict[str, Any]) -> Path:
    """Section 34: who did what, including build failure/fix counts."""
    lines = [f"# {game_id}_AI_ACTIVITY", "",
             f"- Generated: {datetime.now(timezone.utc).isoformat()}", ""]
    for section in ("claude", "codex", "local_llm", "image_ai", "image_to_3d",
                    "blender", "build"):
        lines.append(f"## {section}")
        value = activity.get(section)
        if isinstance(value, dict):
            lines += [f"- {k}: {v}" for k, v in value.items()]
        elif isinstance(value, list):
            lines += [f"- {v}" for v in value]
        else:
            lines.append(f"- {value if value is not None else '(no activity recorded)'}")
        lines.append("")
    paths.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = paths.REPORTS_DIR / f"{game_id}_AI_ACTIVITY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _field_names(template: str) -> list[str]:
    import string
    return [f for _, f, _, _ in string.Formatter().parse(template) if f]
