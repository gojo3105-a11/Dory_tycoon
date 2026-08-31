"""company_state.json - what the pipeline believes, checked against the disk.

Master prompt section 15. The rule that matters here is explicit:

    "State says complete but there is no APK file"
    -> revoke the completion
    -> re-verify that phase

So loading state is not just deserialisation; it is reconciliation. A state
file is a claim, and section 38 forbids treating a claim of success as
success. verify_against_disk() is what turns the claim back into a fact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PHASES = [
    "IDEA", "SCENARIO", "DESIGN_REVIEW", "IMPLEMENTATION_PLAN", "ASSET_PLAN",
    "CHARACTER", "MAP", "CORE_GAMEPLAY", "UI", "PROGRESSION", "POLISH",
    "COMPILE", "CODE_REVIEW", "GAMEPLAY_QA", "ANDROID_BUILD", "APK_VERIFY",
    "REPORT", "COMPLETE",
]


@dataclass
class Discrepancy:
    field_name: str
    claimed: Any
    actual: Any
    action_taken: str


@dataclass
class CompanyState:
    path: Path
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "CompanyState":
        if not path.exists():
            return cls(path=path, data=cls.blank())
        return cls(path=path, data=json.loads(path.read_text(encoding="utf-8-sig")))

    @staticmethod
    def blank() -> dict[str, Any]:
        return {
            "current_game": None,
            "current_phase": None,
            "last_completed_task": None,
            "next_task": None,
            "unity_status": "UNKNOWN",
            "character_status": "UNKNOWN",
            "asset_status": "UNKNOWN",
            "codex_status": "UNKNOWN",
            "ollama_status": "UNKNOWN",
            "build_status": "UNKNOWN",
            "qa_status": "UNKNOWN",
            "retry_count": 0,
            "last_successful_commit": None,
            "games": {},
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    # ---- per game --------------------------------------------------------

    def game(self, game_id: str) -> dict[str, Any]:
        return self.data.setdefault("games", {}).setdefault(
            game_id, {"phase": None, "apk_path": None, "report_path": None}
        )

    def set_phase(self, game_id: str, phase: str) -> None:
        if phase not in PHASES:
            raise ValueError(f"unknown phase {phase!r}; expected one of {PHASES}")
        self.game(game_id)["phase"] = phase

    # ---- reconciliation --------------------------------------------------

    def verify_against_disk(self, repo_root: Path) -> list[Discrepancy]:
        """Revokes any completion the filesystem does not support.

        Section 15's example is the important one: a game marked COMPLETE (or
        past ANDROID_BUILD) whose APK is not on disk is demoted, so the
        pipeline redoes the build instead of trusting a stale claim.
        """
        found: list[Discrepancy] = []

        for game_id, game in self.data.get("games", {}).items():
            phase = game.get("phase")
            if phase not in ("ANDROID_BUILD", "APK_VERIFY", "REPORT", "COMPLETE"):
                continue

            apk_present = self._find_apk(repo_root, game_id) is not None
            if apk_present:
                continue

            found.append(Discrepancy(
                field_name=f"games.{game_id}.phase",
                claimed=phase,
                actual="no .apk/.aab under Builds/%s/" % game_id,
                action_taken="demoted to ANDROID_BUILD for re-verification",
            ))
            game["phase"] = "ANDROID_BUILD"
            game["apk_path"] = None

        if found and self.data.get("build_status") == "SUCCESS":
            found.append(Discrepancy(
                field_name="build_status",
                claimed="SUCCESS",
                actual="at least one game has no APK on disk",
                action_taken="reset to UNKNOWN",
            ))
            self.data["build_status"] = "UNKNOWN"

        return found

    @staticmethod
    def _find_apk(repo_root: Path, game_id: str) -> Path | None:
        build_dir = repo_root / "Builds" / game_id
        if not build_dir.is_dir():
            return None
        for pattern in ("**/*.apk", "**/*.aab"):
            for candidate in build_dir.glob(pattern):
                if candidate.is_file() and candidate.stat().st_size > 0:
                    return candidate
        return None

    def next_phase(self, game_id: str) -> str | None:
        """The phase after the current one, or None at COMPLETE."""
        current = self.game(game_id).get("phase")
        if current is None:
            return PHASES[0]
        if current == "COMPLETE":
            return None
        return PHASES[PHASES.index(current) + 1]
