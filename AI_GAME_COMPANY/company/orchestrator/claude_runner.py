"""Claude Code CLI adapter (master prompt section 2).

The master prompt is explicit: only enable subprocess invocation if the
installed CLI documents a non-interactive mode. We read `claude --help` and
enable it only when `--print` is really there; otherwise Claude Code stays the
human-driven supervisor and the orchestrator keeps running without it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import logging_setup, paths, process_runner
from .policy import Policy

log = logging_setup.get_logger("claude_runner", quiet=True)

OK = "OK"
NOT_INSTALLED = "NOT_INSTALLED"
INTERACTIVE_ONLY = "INTERACTIVE_ONLY"
BLOCKED = "BLOCKED"
ERROR = "ERROR"


@dataclass
class ClaudeResult:
    status: str
    output: str | None = None
    parsed: dict | None = None
    error: str | None = None
    log_path: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == OK


class ClaudeRunner:
    def __init__(self, policy: Policy | None = None, timeout: int = 1800):
        self.policy = policy or Policy.load()
        self.timeout = timeout

    def capabilities(self) -> dict[str, Any]:
        path = process_runner.which("claude")
        if not path:
            return {"installed": False, "status": NOT_INSTALLED,
                    "headless": False, "path": None, "version": None,
                    "note": "Claude Code stays a human-driven supervisor"}
        version = process_runner.probe_version("claude")
        headless = process_runner.supports_flag("claude", "--print")
        return {
            "installed": True,
            "path": path,
            "version": version.get("version"),
            "headless": headless,
            "output_format_json": process_runner.supports_flag("claude", "--output-format"),
            "status": OK if headless else INTERACTIVE_ONLY,
            "note": ("non-interactive mode verified via --help"
                     if headless else
                     "no documented non-interactive flag; subprocess calls stay disabled"),
        }

    def run_prompt(self, prompt: str, *, cwd: Path | str | None = None,
                   allowed_tools: list[str] | None = None,
                   log_name: str = "claude_prompt") -> ClaudeResult:
        if not bool(self.policy.get("use_claude_code")):
            return ClaudeResult(BLOCKED, error="use_claude_code is false")
        caps = self.capabilities()
        if not caps["installed"]:
            return ClaudeResult(NOT_INSTALLED, error="claude CLI not found on PATH")
        if not caps["headless"]:
            return ClaudeResult(
                INTERACTIVE_ONLY,
                error="installed claude CLI documents no --print flag; "
                      "refusing to guess a command (master prompt section 38)")

        cmd = ["claude", "--print"]
        if caps.get("output_format_json"):
            cmd += ["--output-format", "json"]
        if allowed_tools:
            cmd += ["--allowedTools", " ".join(allowed_tools)]
        cmd.append(prompt)

        result = process_runner.run(cmd, cwd=cwd, timeout=self.timeout,
                                    policy=self.policy, log_name=log_name)
        if not result.ok:
            return ClaudeResult(ERROR, output=result.stdout, error=result.tail(20),
                                log_path=result.log_path)
        parsed = None
        try:
            parsed = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            pass
        return ClaudeResult(OK, output=result.stdout, parsed=parsed,
                            log_path=result.log_path)
