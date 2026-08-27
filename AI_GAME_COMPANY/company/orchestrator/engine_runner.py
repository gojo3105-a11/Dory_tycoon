"""Engine-neutral facade over the Godot and Unity adapters.

The master prompt targets Unity; this repository is Godot 4.3. Rather than
pretend one is the other, the pipeline talks to this facade and
config/engines.json decides which adapter answers.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import paths
from .godot_runner import GodotRunner
from .policy import Policy
from .unity_runner import UnityRunner

GODOT, UNITY = "godot", "unity"


def active_engine() -> str:
    if paths.ENGINES_FILE.exists():
        data = json.loads(paths.ENGINES_FILE.read_text(encoding="utf-8"))
        engine = data.get("active_engine", GODOT)
        if engine in (GODOT, UNITY):
            return engine
    return GODOT


class EngineRunner:
    def __init__(self, policy: Policy | None = None, engine: str | None = None):
        self.policy = policy or Policy.load()
        self.engine = engine or active_engine()
        self.impl = (GodotRunner(self.policy) if self.engine == GODOT
                     else UnityRunner(self.policy))

    def capabilities(self) -> dict[str, Any]:
        caps = self.impl.capabilities()
        caps["engine"] = self.engine
        return caps

    def validate(self) -> dict[str, Any]:
        """Compile/import check, whichever the active engine calls it."""
        result = (self.impl.validate_project() if self.engine == GODOT
                  else self.impl.compile_check())
        out = result.to_dict()
        out["engine"] = self.engine
        return out

    def build_android(self, output_path: Path | str) -> dict[str, Any]:
        result = (self.impl.export_android(output_path) if self.engine == GODOT
                  else self.impl.build_android(output_path))
        out = result.to_dict()
        out["engine"] = self.engine
        return out

    def other_engine_status(self) -> dict[str, Any]:
        other = UnityRunner(self.policy) if self.engine == GODOT else GodotRunner(self.policy)
        caps = other.capabilities()
        caps["engine"] = UNITY if self.engine == GODOT else GODOT
        return caps
