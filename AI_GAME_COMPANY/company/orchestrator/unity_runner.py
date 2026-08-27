"""Unity batch-mode adapter (master prompt section 18).

Kept for the Unity games the master prompt plans. The editor path is
discovered, never hardcoded, and a build is SUCCESS only when the exit code,
the Unity build report, and the APK on disk all agree.

Not installed is a reported state, not a crash, so a Godot-only machine can
still run the rest of the pipeline.
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

log = logging_setup.get_logger("unity_runner", quiet=True)

OK = "OK"
NOT_INSTALLED = "NOT_INSTALLED"
NO_PROJECT = "NO_PROJECT"
COMPILE_FAILED = "COMPILE_FAILED"
BUILD_FAILED = "BUILD_FAILED"

_ERROR_PATTERN = re.compile(r"(error CS\d+|Compilation failed|"
                            r"Scripts have compiler errors|Exception:)", re.IGNORECASE)


@dataclass
class UnityResult:
    status: str
    exit_code: int | None = None
    version: str | None = None
    errors: list[str] = field(default_factory=list)
    log_path: str | None = None
    artifact: dict[str, Any] | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == OK

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "exit_code": self.exit_code,
                "version": self.version, "errors": self.errors[:30],
                "log_path": self.log_path, "artifact": self.artifact,
                "detail": self.detail}


class UnityRunner:
    def __init__(self, policy: Policy | None = None,
                 config: dict[str, Any] | None = None, timeout: int = 5400):
        self.policy = policy or Policy.load()
        self.timeout = timeout
        self.config = config if config is not None else self._load_config()
        self.executable = self.discover()

    def _load_config(self) -> dict[str, Any]:
        if paths.ENGINES_FILE.exists():
            return json.loads(paths.ENGINES_FILE.read_text(encoding="utf-8")).get("unity", {})
        return {}

    def discover(self) -> str | None:
        configured = self.config.get("executable")
        if configured and Path(configured).exists():
            return configured
        for var in self.config.get("discovery_env_vars", ["UNITY_BIN", "UNITY_EDITOR_PATH"]):
            value = os.environ.get(var)
            if value and Path(value).exists():
                return value
        found = process_runner.which("unity")
        if found:
            return found
        candidates: list[str] = []
        for pattern in self.config.get("discovery_globs", []):
            candidates += sorted(glob.glob(os.path.expanduser(pattern)))
        # Highest editor version wins when several Hub installs exist.
        return candidates[-1] if candidates else None

    def project_path(self) -> Path | None:
        configured = self.config.get("project_path")
        if not configured:
            return None
        p = Path(configured)
        if not p.is_absolute():
            p = (paths.ROOT / p).resolve()
        return p if (p / "Assets").is_dir() else None

    def capabilities(self) -> dict[str, Any]:
        if not self.executable:
            return {"installed": False, "status": NOT_INSTALLED, "path": None,
                    "version": None, "project": None,
                    "hint": "install Unity or set UNITY_BIN; the Godot adapter "
                            "runs this repository in the meantime"}
        version = None
        match = re.search(r"Editor[/\\]([0-9][^/\\]*)", self.executable)
        if match:
            version = match.group(1)
        project = self.project_path()
        return {"installed": True, "status": OK, "path": self.executable,
                "version": version, "project": str(project) if project else None}

    def _base_cmd(self, project: Path, log_file: Path) -> list[str]:
        return [self.executable, "-batchmode", "-quit", "-nographics",
                "-projectPath", str(project), "-logFile", str(log_file)]

    def compile_check(self, project: Path | None = None) -> UnityResult:
        caps = self.capabilities()
        if not caps["installed"]:
            return UnityResult(NOT_INSTALLED, detail=caps.get("hint"))
        project = project or self.project_path()
        if project is None:
            return UnityResult(NO_PROJECT,
                               detail="config/engines.json unity.project_path is not set "
                                      "to a folder containing Assets/")
        unity_log = paths.LOGS_DIR / "unity_compile.log"
        cmd = self._base_cmd(project, unity_log)
        method = self.config.get("compile_method")
        if method:
            cmd += ["-executeMethod", method]
        result = process_runner.run(cmd, timeout=self.timeout, policy=self.policy,
                                    log_name="unity_compile")
        editor_log = unity_log.read_text(encoding="utf-8", errors="replace") if unity_log.exists() else ""
        errors = [ln.strip()[:400] for ln in editor_log.splitlines()
                  if _ERROR_PATTERN.search(ln)]
        status = OK if (result.ok and not errors) else COMPILE_FAILED
        return UnityResult(status, exit_code=result.exit_code, version=caps.get("version"),
                           errors=errors, log_path=result.log_path,
                           detail=None if status == OK else
                           f"{len(errors)} compiler error line(s); exit={result.exit_code}")

    def build_android(self, output_apk: Path | str,
                      project: Path | None = None) -> UnityResult:
        caps = self.capabilities()
        if not caps["installed"]:
            return UnityResult(NOT_INSTALLED, detail=caps.get("hint"))
        project = project or self.project_path()
        if project is None:
            return UnityResult(NO_PROJECT, detail="unity.project_path is not set")
        method = self.config.get("build_method")
        if not method:
            return UnityResult(BUILD_FAILED,
                               detail="unity.build_method is not configured; an Editor "
                                      "script (Assets/Editor/GameFactoryBuild.cs) must "
                                      "expose a static build method")
        output_apk = Path(output_apk)
        output_apk.parent.mkdir(parents=True, exist_ok=True)
        output_apk.unlink(missing_ok=True)
        unity_log = paths.LOGS_DIR / "unity_build.log"
        cmd = self._base_cmd(project, unity_log) + [
            "-executeMethod", method,
            "-buildTarget", self.config.get("build_target", "Android"),
            "-outputPath", str(output_apk),
        ]
        result = process_runner.run(cmd, timeout=self.timeout, policy=self.policy,
                                    log_name="unity_build")
        apk_check = artifact_validator.apk_valid(output_apk)
        editor_log = unity_log.read_text(encoding="utf-8", errors="replace") if unity_log.exists() else ""
        errors = [ln.strip()[:400] for ln in editor_log.splitlines()
                  if _ERROR_PATTERN.search(ln)]
        ok = result.ok and apk_check["ok"] and not errors
        return UnityResult(OK if ok else BUILD_FAILED, exit_code=result.exit_code,
                           version=caps.get("version"), errors=errors,
                           log_path=result.log_path, artifact=apk_check,
                           detail=None if ok else
                           f"exit={result.exit_code} apk_ok={apk_check['ok']} "
                           f"errors={len(errors)}")
