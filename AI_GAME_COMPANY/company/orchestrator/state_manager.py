"""company_state.json with atomic writes and disk verification (section 15).

The rule that matters: state claiming a phase is complete is not evidence.
`verify_against_disk()` re-checks the declared artifacts and revokes the
completion when the file is not actually there.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import logging_setup, paths

log = logging_setup.get_logger("state_manager", quiet=True)

INITIAL_STATE: dict[str, Any] = {
    "schema_version": 1,
    "current_game": None,
    "current_phase": "INFRASTRUCTURE",
    "last_completed_task": None,
    "next_task": None,
    "engine": "godot",
    "engine_status": "UNKNOWN",
    "unity_status": "NOT_INSTALLED",
    "godot_status": "UNKNOWN",
    "character_status": "NOT_STARTED",
    "asset_status": "NOT_STARTED",
    "codex_status": "UNKNOWN",
    "ollama_status": "UNKNOWN",
    "claude_status": "UNKNOWN",
    "blender_status": "UNKNOWN",
    "build_status": "NOT_STARTED",
    "qa_status": "NOT_STARTED",
    "retry_count": 0,
    "last_successful_commit": None,
    "last_error": None,
    "completed_apk_count": 0,
    "artifacts": {},
    "updated_at": None,
    "history": [],
}

_MAX_HISTORY = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StateManager:
    path: Path = paths.STATE_FILE

    # ---- io ----------------------------------------------------------
    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(INITIAL_STATE)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.error("state file unreadable (%s); falling back to initial state", exc)
            backup = self.path.with_suffix(".corrupt.json")
            try:
                self.path.replace(backup)
                log.error("corrupt state moved to %s", paths.rel(backup))
            except OSError:
                pass
            return dict(INITIAL_STATE)
        merged = dict(INITIAL_STATE)
        merged.update(data)
        return merged

    def save(self, state: dict[str, Any]) -> Path:
        """Atomic write so a crash mid-save cannot corrupt the state file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        state["updated_at"] = _now()
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        finally:
            if Path(tmp).exists():
                Path(tmp).unlink(missing_ok=True)
        return self.path

    def init(self, *, force: bool = False) -> dict[str, Any]:
        if self.path.exists() and not force:
            return self.load()
        state = dict(INITIAL_STATE)
        state["history"] = [{"at": _now(), "event": "state_initialised"}]
        self.save(state)
        return state

    # ---- mutation ----------------------------------------------------
    def update(self, **fields: Any) -> dict[str, Any]:
        state = self.load()
        changed = {k: v for k, v in fields.items() if state.get(k) != v}
        state.update(fields)
        if changed:
            state.setdefault("history", []).append(
                {"at": _now(), "event": "update", "changed": list(changed)})
            state["history"] = state["history"][-_MAX_HISTORY:]
        self.save(state)
        return state

    def record_event(self, event: str, **detail: Any) -> dict[str, Any]:
        state = self.load()
        entry = {"at": _now(), "event": event}
        entry.update(detail)
        state.setdefault("history", []).append(entry)
        state["history"] = state["history"][-_MAX_HISTORY:]
        self.save(state)
        return state

    def register_artifact(self, key: str, path: Path | str,
                          *, required: bool = True) -> dict[str, Any]:
        state = self.load()
        state.setdefault("artifacts", {})[key] = {
            "path": str(path),
            "required": required,
            "registered_at": _now(),
        }
        self.save(state)
        return state

    # ---- verification (section 15) -----------------------------------
    def verify_against_disk(self) -> dict[str, Any]:
        """Revoke completions whose artifacts are missing on disk."""
        state = self.load()
        problems: list[dict[str, Any]] = []
        for key, meta in (state.get("artifacts") or {}).items():
            p = Path(meta["path"])
            if not p.is_absolute():
                p = paths.ROOT / p
            if not p.exists():
                problems.append({"artifact": key, "path": str(p), "issue": "MISSING"})
            elif p.is_file() and p.stat().st_size == 0:
                problems.append({"artifact": key, "path": str(p), "issue": "EMPTY"})

        apk_keys = [k for k, m in (state.get("artifacts") or {}).items()
                    if str(m.get("path", "")).endswith((".apk", ".aab"))]
        apk_problems = [p for p in problems if p["artifact"] in apk_keys]
        if apk_problems and state.get("build_status") in ("SUCCESS", "COMPLETE"):
            state["build_status"] = "REVOKED_ARTIFACT_MISSING"
            state["last_error"] = "build_status claimed success but APK is missing on disk"
            state.setdefault("history", []).append(
                {"at": _now(), "event": "completion_revoked", "detail": apk_problems})
            self.save(state)

        return {
            "verified_at": _now(),
            "artifact_count": len(state.get("artifacts") or {}),
            "problems": problems,
            "build_status": state.get("build_status"),
            "consistent": not problems,
        }

    def summary(self) -> dict[str, Any]:
        state = self.load()
        keys = ("current_game", "current_phase", "engine", "engine_status",
                "codex_status", "ollama_status", "claude_status", "blender_status",
                "build_status", "qa_status", "retry_count", "completed_apk_count",
                "last_completed_task", "next_task", "last_error", "updated_at")
        return {k: state.get(k) for k in keys}
