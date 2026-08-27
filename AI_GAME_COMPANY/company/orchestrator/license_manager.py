"""LICENSE_REGISTRY.json (master prompt section 8).

Two rules encoded here: an UNKNOWN entry can never ship, and a code license
is tracked separately from a model-weight license - "the code is MIT so the
weights are MIT" is not an inference this module allows.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths

APPROVED, REJECTED, UNKNOWN = "APPROVED", "REJECTED", "UNKNOWN"
VALID_STATUSES = (APPROVED, REJECTED, UNKNOWN)

ASSET_TYPES = ("ai_model", "model_weights", "code", "asset", "sound",
               "texture", "3d_model", "font", "animation")


@dataclass
class LicenseEntry:
    id: str
    name: str
    type: str
    source: str
    version: str | None = None
    license: str = "UNVERIFIED"
    code_license: str | None = None
    weights_license: str | None = None
    commercial_use: bool | None = None
    attribution_required: bool | None = None
    redistribution_rules: str | None = None
    verified_at: str | None = None
    verified_by: str | None = None
    games: list[str] = field(default_factory=list)
    status: str = UNKNOWN
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LicenseManager:
    def __init__(self, path: Path | None = None):
        self.path = path or paths.LICENSE_REGISTRY_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"schema_version": 1, "entries": [],
                         "created_at": datetime.now(timezone.utc).isoformat()})

    # ---- io ----------------------------------------------------------
    def _read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                             encoding="utf-8")

    # ---- api ---------------------------------------------------------
    def register(self, entry: LicenseEntry) -> LicenseEntry:
        if entry.status not in VALID_STATUSES:
            raise ValueError(f"invalid status {entry.status}")
        if entry.status == APPROVED and not entry.verified_by:
            raise ValueError("APPROVED requires verified_by (who checked the license)")
        if entry.status == APPROVED and entry.commercial_use is not True:
            raise ValueError("APPROVED requires commercial_use=True")
        data = self._read()
        entries = [e for e in data["entries"] if e["id"] != entry.id]
        if entry.status == APPROVED and not entry.verified_at:
            entry.verified_at = datetime.now(timezone.utc).isoformat()
        entries.append(entry.to_dict())
        data["entries"] = sorted(entries, key=lambda e: e["id"])
        self._write(data)
        return entry

    def get(self, entry_id: str) -> dict[str, Any] | None:
        return next((e for e in self._read()["entries"] if e["id"] == entry_id), None)

    def all(self) -> list[dict[str, Any]]:
        return self._read()["entries"]

    def by_status(self, status: str) -> list[dict[str, Any]]:
        return [e for e in self.all() if e.get("status") == status]

    def is_production_usable(self, entry_id: str) -> tuple[bool, str]:
        entry = self.get(entry_id)
        if entry is None:
            return False, f"{entry_id} is not in the registry (treated as UNKNOWN)"
        if entry.get("status") != APPROVED:
            return False, f"{entry_id} status is {entry.get('status')}"
        if entry.get("commercial_use") is not True:
            return False, f"{entry_id} has commercial_use={entry.get('commercial_use')}"
        return True, "APPROVED"

    def release_gate(self, used_ids: list[str]) -> dict[str, Any]:
        """Block a release that contains any non-APPROVED asset (section 8)."""
        blockers = []
        for entry_id in used_ids:
            ok, reason = self.is_production_usable(entry_id)
            if not ok:
                blockers.append({"id": entry_id, "reason": reason})
        return {
            "checked": len(used_ids),
            "blockers": blockers,
            "release_allowed": not blockers,
            "attribution_required": [
                e["id"] for e in self.all()
                if e["id"] in used_ids and e.get("attribution_required")
            ],
        }
