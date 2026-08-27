"""Codex CLI adapter (master prompt section 3, 17).

Security rules encoded here: the auth file is never read or copied,
OPENAI_API_KEY is never forwarded (policy sanitises the child env), and hitting
a usage limit produces CODEX_LIMITED with a fallback plan instead of switching
to paid API billing.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import logging_setup, paths, process_runner
from .policy import Policy

log = logging_setup.get_logger("codex_runner", quiet=True)

OK = "OK"
NOT_INSTALLED = "NOT_INSTALLED"
NOT_LOGGED_IN = "NOT_LOGGED_IN"
CODEX_LIMITED = "CODEX_LIMITED"
ERROR = "ERROR"
BLOCKED = "BLOCKED"

_LIMIT_PATTERNS = (
    r"rate limit", r"usage limit", r"quota", r"too many requests",
    r"429", r"limit reached", r"try again later",
)
_AUTH_PATTERNS = (r"not logged in", r"unauthorized", r"401", r"please run .*login",
                  r"authentication")

REVIEW_CHECKLIST = [
    "Compile errors", "NullReference", "Event unsubscribe", "Memory allocation",
    "Update() overuse", "Coroutine lifecycle", "Serialization", "Save corruption",
    "Android compatibility", "Touch input", "Scene reference", "Asset reference",
    "Performance", "Race condition", "Missing reference", "Build configuration",
]


@dataclass
class CodexResult:
    status: str
    output: str | None = None
    parsed: dict | list | None = None
    error: str | None = None
    log_path: str | None = None
    fallback: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == OK


class CodexRunner:
    def __init__(self, policy: Policy | None = None, timeout: int = 900):
        self.policy = policy or Policy.load()
        self.timeout = timeout

    def capabilities(self) -> dict[str, Any]:
        """Read the installed --help before using any subcommand (STEP 5)."""
        path = process_runner.which("codex")
        if not path:
            return {"installed": False, "status": NOT_INSTALLED, "exec": False,
                    "json": False, "path": None, "version": None}
        version = process_runner.probe_version("codex")
        return {
            "installed": True,
            "path": path,
            "version": version.get("version"),
            "status": OK,
            "exec": process_runner.supports_flag("codex", "exec"),
            "json": process_runner.supports_flag("codex", "--json"),
        }

    def _classify(self, text: str) -> str | None:
        low = (text or "").lower()
        if any(re.search(p, low) for p in _LIMIT_PATTERNS):
            return CODEX_LIMITED
        if any(re.search(p, low) for p in _AUTH_PATTERNS):
            return NOT_LOGGED_IN
        return None

    def review(self, instruction: str, *, cwd: Path | str | None = None,
               want_json: bool = True, log_name: str = "codex_review") -> CodexResult:
        if not bool(self.policy.get("use_codex_subscription")):
            return CodexResult(BLOCKED, error="use_codex_subscription is false",
                               fallback="local_llm_then_claude")
        caps = self.capabilities()
        if not caps["installed"]:
            return CodexResult(NOT_INSTALLED,
                               error="codex CLI not found on PATH",
                               fallback="local_llm_then_claude")
        if not caps["exec"]:
            return CodexResult(ERROR,
                               error="installed codex has no documented 'exec' "
                                     "subcommand; refusing to guess a command "
                                     "(master prompt section 38)",
                               fallback="local_llm_then_claude")

        cmd = ["codex", "exec"]
        if want_json and caps["json"]:
            cmd.append("--json")
        cmd.append(instruction)

        # policy.sanitized_env() removes OPENAI_API_KEY so the subscription
        # session is used and no metered API call can start.
        result = process_runner.run(cmd, cwd=cwd, timeout=self.timeout,
                                    policy=self.policy, log_name=log_name)
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        classified = self._classify(combined)
        if classified:
            return CodexResult(classified, output=result.stdout,
                               error=result.tail(15), log_path=result.log_path,
                               fallback="local_llm_then_claude")
        if not result.ok:
            return CodexResult(ERROR, output=result.stdout, error=result.tail(20),
                               log_path=result.log_path,
                               fallback="local_llm_then_claude")
        return CodexResult(OK, output=result.stdout,
                           parsed=_try_json(result.stdout),
                           log_path=result.log_path)

    def review_changes(self, *, project_root: Path | str, engine: str,
                       engine_version: str | None, changed_files: list[str],
                       acceptance_criteria: list[str],
                       error_log: str | None = None) -> CodexResult:
        """Structured code review request (section 17)."""
        instruction = build_review_prompt(
            engine=engine, engine_version=engine_version,
            changed_files=changed_files,
            acceptance_criteria=acceptance_criteria,
            error_log=error_log)
        return self.review(instruction, cwd=project_root)


def build_review_prompt(*, engine: str, engine_version: str | None,
                        changed_files: list[str], acceptance_criteria: list[str],
                        error_log: str | None = None) -> str:
    checklist = "\n".join(f"- {item}" for item in REVIEW_CHECKLIST)
    files = "\n".join(f"- {f}" for f in changed_files) or "- (none listed)"
    criteria = "\n".join(f"- {c}" for c in acceptance_criteria) or "- (none listed)"
    log_block = f"\n\nRELEVANT ERROR LOG:\n{error_log[-4000:]}" if error_log else ""
    return (
        f"You are reviewing a {engine} ({engine_version or 'version unknown'}) "
        "mobile game project targeting Android.\n\n"
        f"CHANGED FILES:\n{files}\n\n"
        f"ACCEPTANCE CRITERIA:\n{criteria}\n\n"
        f"CHECK FOR:\n{checklist}{log_block}\n\n"
        "Return JSON only, with this shape:\n"
        '{"critical": [{"file": "", "line": 0, "issue": "", "why": "", "fix": ""}], '
        '"major": [], "minor": [], "verdict": "PASS|FAIL"}'
    )


def _try_json(text: str | None) -> dict | list | None:
    if not text:
        return None
    for candidate in _json_candidates(text):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _json_candidates(text: str) -> list[str]:
    out = [text.strip()]
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fence:
        out.append(fence.group(1).strip())
    brace = re.search(r"(\{.*\})", text, re.DOTALL)
    if brace:
        out.append(brace.group(1))
    return out
