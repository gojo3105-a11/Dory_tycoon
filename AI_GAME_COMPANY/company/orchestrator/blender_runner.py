"""Blender background runner (master prompt section 11).

Success needs both a zero exit code AND the expected output file: a Blender
script can exit 0 having exported nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from . import artifact_validator, logging_setup, paths, process_runner
from .policy import Policy

log = logging_setup.get_logger("blender_runner", quiet=True)

OK = "OK"
NOT_INSTALLED = "NOT_INSTALLED"
SCRIPT_FAILED = "SCRIPT_FAILED"
NO_OUTPUT = "NO_OUTPUT"


@dataclass
class BlenderResult:
    status: str
    exit_code: int | None = None
    output_files: list[str] = None
    log_path: str | None = None
    error: str | None = None

    def __post_init__(self):
        self.output_files = self.output_files or []

    @property
    def ok(self) -> bool:
        return self.status == OK


class BlenderRunner:
    def __init__(self, policy: Policy | None = None, executable: str | None = None,
                 timeout: int = 1800):
        self.policy = policy or Policy.load()
        self.executable = executable or "blender"
        self.timeout = timeout

    def capabilities(self) -> dict[str, Any]:
        path = process_runner.which(self.executable)
        if not path:
            return {"installed": False, "status": NOT_INSTALLED, "path": None,
                    "version": None, "background": False, "python": False}
        version = process_runner.probe_version(self.executable)
        return {
            "installed": True,
            "path": path,
            "version": version.get("version"),
            "background": process_runner.supports_flag(self.executable, "--background"),
            "python": process_runner.supports_flag(self.executable, "--python"),
            "status": OK,
        }

    def run_script(self, script: Path | str, *,
                   expected_outputs: Sequence[Path | str] = (),
                   script_args: Sequence[str] = (),
                   log_name: str = "blender") -> BlenderResult:
        caps = self.capabilities()
        if not caps["installed"]:
            return BlenderResult(NOT_INSTALLED,
                                 error=f"{self.executable} not found on PATH")
        script = Path(script)
        if not script.exists():
            return BlenderResult(SCRIPT_FAILED, error=f"script missing: {script}")

        cmd = [self.executable, "--background", "--factory-startup",
               "--python", str(script)]
        if script_args:
            cmd += ["--", *[str(a) for a in script_args]]
        result = process_runner.run(cmd, timeout=self.timeout, policy=self.policy,
                                   log_name=log_name)
        if not result.ok:
            return BlenderResult(SCRIPT_FAILED, exit_code=result.exit_code,
                                 log_path=result.log_path, error=result.tail(25))
        if expected_outputs:
            check = artifact_validator.all_files_exist(list(expected_outputs))
            if not check["ok"]:
                return BlenderResult(NO_OUTPUT, exit_code=result.exit_code,
                                     log_path=result.log_path,
                                     error=f"exit 0 but missing outputs: {check['missing']}")
        return BlenderResult(OK, exit_code=result.exit_code,
                             output_files=[str(p) for p in expected_outputs],
                             log_path=result.log_path)

    def selftest(self) -> BlenderResult:
        """Prove the background pipeline works end to end (checklist item)."""
        script = paths.BLENDER_TOOLS_DIR / "selftest.py"
        out = paths.STATE_DIR / "blender_selftest.txt"
        out.unlink(missing_ok=True)
        return self.run_script(script, expected_outputs=[out],
                               script_args=[str(out)], log_name="blender_selftest")
