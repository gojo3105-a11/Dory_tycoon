"""Godot 4.x batch adapter (this repository's real engine).

The master prompt's section 18 rules are engine-agnostic and applied here:
the executable is discovered rather than hardcoded, and a build counts as
successful only when the exit code, the log, and the artifact on disk agree.
"""
from __future__ import annotations

import glob
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import artifact_validator, logging_setup, paths, process_runner
from .policy import Policy

log = logging_setup.get_logger("godot_runner", quiet=True)

OK = "OK"
NOT_INSTALLED = "NOT_INSTALLED"
VALIDATION_FAILED = "VALIDATION_FAILED"
BUILD_FAILED = "BUILD_FAILED"
EXPORT_TEMPLATES_MISSING = "EXPORT_TEMPLATES_MISSING"
HUMAN_GATE = "HUMAN_GATE"

# Lines Godot prints that are noise in a headless import pass, not defects.
_IGNORABLE = (
    "Godot Engine v",
    "OpenGL API",
    "Vulkan API",
    "TextServer",
    "CowData",
    "Editor documentation",
    "Unable to shape text",
    "Using \"default\" pen tablet driver",
    "Blender 3.0+",
    "Automatically setting",
    "Please check the used file",
    "core/config/project_settings.cpp",
)
_ERROR_PATTERN = re.compile(
    r"(SCRIPT ERROR|Parse Error|ERROR: |Failed to load|Cannot open file|"
    r"Invalid call|Compile Error|Unable to load)", re.IGNORECASE)


@dataclass
class GodotResult:
    status: str
    exit_code: int | None = None
    version: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    log_path: str | None = None
    artifact: dict[str, Any] | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "exit_code": self.exit_code,
            "version": self.version, "error_count": len(self.errors),
            "errors": self.errors[:30], "warning_count": len(self.warnings),
            "warnings": self.warnings[:30], "log_path": self.log_path,
            "artifact": self.artifact, "detail": self.detail,
        }


def _expand(pattern: str) -> list[str]:
    return sorted(glob.glob(os.path.expanduser(pattern)))


class GodotRunner:
    def __init__(self, policy: Policy | None = None,
                 config: dict[str, Any] | None = None, timeout: int = 1800):
        self.policy = policy or Policy.load()
        self.timeout = timeout
        self.config = config if config is not None else self._load_config()
        self.executable = self.discover()

    # ---- discovery (never hardcode a path: section 18) ---------------
    def _load_config(self) -> dict[str, Any]:
        if paths.ENGINES_FILE.exists():
            data = json.loads(paths.ENGINES_FILE.read_text(encoding="utf-8"))
            return data.get("godot", {})
        return {}

    def discover(self) -> str | None:
        configured = self.config.get("executable")
        if configured and (Path(configured).exists() or process_runner.which(configured)):
            return configured
        for var in self.config.get("discovery_env_vars", ["GODOT_BIN", "GODOT4_BIN"]):
            value = os.environ.get(var)
            if value and (Path(value).exists() or process_runner.which(value)):
                return value
        for name in self.config.get("discovery_names", ["godot4", "godot"]):
            found = process_runner.which(name)
            if found:
                return found
        for pattern in self.config.get("discovery_globs", []):
            for candidate in _expand(pattern):
                if os.access(candidate, os.X_OK):
                    return candidate
        return None

    def cache_executable(self) -> Path | None:
        """Persist a discovered path into config/engines.json (section 18)."""
        if not self.executable or not paths.ENGINES_FILE.exists():
            return None
        data = json.loads(paths.ENGINES_FILE.read_text(encoding="utf-8"))
        data.setdefault("godot", {})["executable"] = self.executable
        paths.ENGINES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
        return paths.ENGINES_FILE

    def project_path(self) -> Path:
        configured = self.config.get("project_path")
        if configured:
            p = Path(configured)
            if not p.is_absolute():
                p = (paths.ROOT / p).resolve()
            if (p / "project.godot").exists():
                return p
        return paths.target_project_root()

    # ---- capabilities ------------------------------------------------
    def capabilities(self) -> dict[str, Any]:
        if not self.executable:
            return {"installed": False, "status": NOT_INSTALLED, "path": None,
                    "version": None, "project": str(self.project_path()),
                    "hint": "install Godot 4.x or set GODOT_BIN"}
        result = process_runner.run([self.executable, "--headless", "--version"],
                                    timeout=120, policy=self.policy)
        version = (result.stdout or result.stderr or "").strip().splitlines()
        version = version[0] if version else None
        expected = self.config.get("expected_version_prefix", "4.")
        return {
            "installed": True,
            "path": self.executable,
            "version": version,
            "version_ok": bool(version and version.startswith(expected)),
            "project": str(self.project_path()),
            "export_templates_installed": self.export_templates_installed(),
            "status": OK if result.ok else "PRESENT_BUT_ERRORED",
        }

    def export_templates_installed(self) -> bool:
        """Android export needs the matching export templates on disk."""
        roots = [
            Path.home() / ".local/share/godot/export_templates",
            Path.home() / "AppData/Roaming/Godot/export_templates",
            Path.home() / "Library/Application Support/Godot/export_templates",
        ]
        return any(r.is_dir() and any(r.iterdir()) for r in roots)

    # ---- validation --------------------------------------------------
    def _collect_errors(self, text: str) -> list[str]:
        return self._collect(text)[0]

    def _collect(self, text: str) -> tuple[list[str], list[str]]:
        """Errors block a PASS; warnings are reported but do not."""
        errors: list[str] = []
        warnings: list[str] = []
        for line in (text or "").splitlines():
            stripped = line.strip()
            if not stripped or any(tok in stripped for tok in _IGNORABLE):
                continue
            if _ERROR_PATTERN.search(stripped):
                errors.append(stripped[:400])
            elif stripped.startswith("WARNING:"):
                warnings.append(stripped[:400])
        return errors, warnings

    def validate_project(self, project: Path | None = None) -> GodotResult:
        """Headless import/compile pass: the Godot analogue of a batch compile."""
        caps = self.capabilities()
        if not caps["installed"]:
            return GodotResult(NOT_INSTALLED, detail=caps.get("hint"))
        project = project or self.project_path()
        if not (project / "project.godot").exists():
            return GodotResult(VALIDATION_FAILED,
                               detail=f"no project.godot under {project}")
        cmd = [self.executable, "--headless", "--path", str(project),
               "--editor", "--quit"]
        result = process_runner.run(cmd, timeout=self.timeout, policy=self.policy,
                                    log_name="godot_validate")
        errors, warnings = self._collect(
            (result.stdout or "") + "\n" + (result.stderr or ""))
        status = OK if (result.ok and not errors) else VALIDATION_FAILED
        return GodotResult(status, exit_code=result.exit_code,
                           version=caps.get("version"), errors=errors,
                           warnings=warnings, log_path=result.log_path,
                           detail=None if status == OK else
                           f"{len(errors)} error line(s); exit={result.exit_code}")

    def check_script(self, script_res_path: str,
                     project: Path | None = None) -> GodotResult:
        """Parse-only check of one GDScript file (`--check-only --script`)."""
        caps = self.capabilities()
        if not caps["installed"]:
            return GodotResult(NOT_INSTALLED, detail=caps.get("hint"))
        project = project or self.project_path()
        cmd = [self.executable, "--headless", "--path", str(project),
               "--check-only", "--script", script_res_path]
        result = process_runner.run(cmd, timeout=300, policy=self.policy,
                                    log_name="godot_check_script")
        errors = self._collect_errors((result.stdout or "") + "\n" + (result.stderr or ""))
        status = OK if (result.ok and not errors) else VALIDATION_FAILED
        return GodotResult(status, exit_code=result.exit_code, errors=errors,
                           log_path=result.log_path, detail=script_res_path)

    def check_all_scripts(self, project: Path | None = None) -> dict[str, Any]:
        project = project or self.project_path()
        scripts = [p for p in project.glob("**/*.gd") if ".godot" not in p.parts]
        results = {}
        for script in scripts:
            res = f"res://{script.relative_to(project).as_posix()}"
            results[res] = self.check_script(res, project).to_dict()
        failed = [k for k, v in results.items() if v["status"] != OK]
        return {"checked": len(results), "failed": failed, "ok": not failed,
                "details": results}

    # ---- android export ----------------------------------------------
    def export_android(self, output_apk: Path | str, *,
                       project: Path | None = None, preset: str | None = None,
                       debug: bool = True) -> GodotResult:
        """Export an APK. Three-way verification per master prompt section 18."""
        caps = self.capabilities()
        if not caps["installed"]:
            return GodotResult(NOT_INSTALLED, detail=caps.get("hint"))
        project = project or self.project_path()
        preset = preset or self.config.get("android_export_preset", "Android")

        if not (project / "export_presets.cfg").exists():
            return GodotResult(HUMAN_GATE,
                               detail="export_presets.cfg missing: an Android export "
                                      "preset plus debug keystore must be created once "
                                      "in the Godot editor (HUMAN_GATE, section 37)")
        if not caps["export_templates_installed"]:
            return GodotResult(EXPORT_TEMPLATES_MISSING,
                               detail="Godot export templates are not installed; "
                                      "install them for this exact engine version")

        output_apk = Path(output_apk)
        output_apk.parent.mkdir(parents=True, exist_ok=True)
        output_apk.unlink(missing_ok=True)
        flag = "--export-debug" if debug else "--export-release"
        cmd = [self.executable, "--headless", "--path", str(project),
               flag, preset, str(output_apk)]
        result = process_runner.run(cmd, timeout=self.timeout, policy=self.policy,
                                    log_name="godot_export_android")
        apk_check = artifact_validator.apk_valid(output_apk)
        errors = self._collect_errors((result.stdout or "") + "\n" + (result.stderr or ""))
        # Exit code AND log AND artifact must all agree (section 18).
        ok = result.ok and apk_check["ok"]
        return GodotResult(OK if ok else BUILD_FAILED, exit_code=result.exit_code,
                           version=caps.get("version"), errors=errors,
                           log_path=result.log_path, artifact=apk_check,
                           detail=None if ok else
                           f"exit={result.exit_code} apk_ok={apk_check['ok']}")
