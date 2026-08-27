"""Single choke point for every external process (master prompt section 43).

Every run records EXPECTED / ACTUAL / STATUS / LOG_PATH so a result can be
audited later, and runs with a policy-sanitised environment.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Sequence

from . import logging_setup, paths
from .policy import Policy

log = logging_setup.get_logger("process_runner", quiet=True)


@dataclass
class RunResult:
    command: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    duration_s: float
    log_path: str | None
    timed_out: bool = False
    launched: bool = True
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.launched and not self.timed_out and self.exit_code == 0

    def tail(self, n: int = 40) -> str:
        text = (self.stdout or "") + ("\n" + self.stderr if self.stderr else "")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return "\n".join(lines[-n:])

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ok"] = self.ok
        # Keep reports small; the full text is in the log file.
        d["stdout"] = self.stdout[-4000:]
        d["stderr"] = self.stderr[-4000:]
        return d


def which(name: str) -> str | None:
    return shutil.which(name)


def run(command: Sequence[str], *, cwd: Path | str | None = None,
        timeout: int = 600, policy: Policy | None = None,
        log_name: str | None = None, env_extra: dict[str, str] | None = None,
        input_text: str | None = None) -> RunResult:
    """Run `command`, never raising on tool failure - failures are data."""
    policy = policy or Policy.load()
    cmd = [str(c) for c in command]
    env = policy.sanitized_env(extra=env_extra)
    started = time.time()

    if not cmd:
        return RunResult(cmd, None, "", "empty command", 0.0, None,
                         launched=False, error="empty command")

    exe = cmd[0]
    if not (os.path.sep in exe or shutil.which(exe) or Path(exe).exists()):
        return RunResult(cmd, None, "", f"executable not found: {exe}", 0.0, None,
                         launched=False, error="NOT_INSTALLED")

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            input=input_text,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        stdout, stderr, code, timed_out = proc.stdout, proc.stderr, proc.returncode, False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (
            exc.stdout.decode("utf-8", "replace") if exc.stdout else "")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (
            exc.stderr.decode("utf-8", "replace") if exc.stderr else "")
        stderr += f"\n[process_runner] TIMEOUT after {timeout}s"
        code, timed_out = None, True
    except OSError as exc:
        return RunResult(cmd, None, "", str(exc), time.time() - started, None,
                         launched=False, error=f"OSError: {exc}")

    duration = time.time() - started
    log_path = None
    if log_name:
        body = (
            f"COMMAND : {' '.join(cmd)}\n"
            f"CWD     : {cwd or os.getcwd()}\n"
            f"EXIT    : {code}\n"
            f"TIMEOUT : {timed_out}\n"
            f"DURATION: {duration:.2f}s\n"
            f"--- STDOUT ---\n{stdout}\n--- STDERR ---\n{stderr}\n"
        )
        log_path = str(paths.rel(logging_setup.write_log_file(log_name, body)))

    log.debug("ran %s exit=%s duration=%.2fs", cmd[0], code, duration)
    return RunResult(cmd, code, stdout, stderr, duration, log_path, timed_out=timed_out)


def probe_version(name: str, args: Sequence[str] = ("--version",),
                  timeout: int = 30) -> dict:
    """Detect a CLI without assuming it exists (master prompt section 38)."""
    path = shutil.which(name)
    if not path:
        return {"installed": False, "version": None, "path": None, "status": "MISSING"}
    result = run([name, *args], timeout=timeout)
    version = None
    if result.launched:
        text = (result.stdout or result.stderr or "").strip()
        version = text.splitlines()[0][:200] if text else None
    return {
        "installed": True,
        "version": version,
        "path": path,
        "status": "OK" if result.ok else "PRESENT_BUT_ERRORED",
        "exit_code": result.exit_code,
    }


def supports_flag(name: str, flag: str, timeout: int = 30) -> bool:
    """Read the real --help output before using a flag (master prompt STEP 5)."""
    if not shutil.which(name):
        return False
    result = run([name, "--help"], timeout=timeout)
    text = (result.stdout or "") + (result.stderr or "")
    return flag in text
