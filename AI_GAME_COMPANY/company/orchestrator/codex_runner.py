"""Codex as reviewer AND as co-developer. Sections 3, 7 and STEP 5.

Two entry points, deliberately separated by two different policy gates:

  review()     read-only. Codex inspects the tree and reports.
  implement()  workspace-write. Codex edits the tree itself, so that it and
               Claude can split the work on the shared board (teamwork.py)
               instead of one of them doing everything and the other only
               commenting. Requires allow_codex_write ON TOP of the
               subscription gate - enabling the reviewer must not silently
               grant write access.


Every flag used here was read from config/cli-probes/codex.txt, captured from
codex-cli 0.151.0 on the build PC. Section 41 STEP 5 forbids writing this
adapter against a guessed interface, and that rule already earned its keep:
`-a/--ask-for-approval` exists on the top-level `codex` command but NOT on
`codex exec`, so passing it here would have failed every run.

Three policy rules are enforced in code rather than left to documentation:

  SUBSCRIPTION ONLY (section 3, section 7)
      use_codex_subscription must be true, and allow_openai_api_billing being
      false means the blocked API keys are STRIPPED from the subprocess
      environment. Codex would otherwise happily pick up OPENAI_API_KEY and
      bill it. Presence of a key is not permission to spend it.

  DEGRADE, NEVER SPEND (section 3, on_codex_limit)
      Hitting the subscription limit returns CODEX_LIMITED so the caller can
      fall back to a local or Claude review. It never escalates to a paid API.

  A REVIEW THAT DID NOT RUN IS NOT A CLEAN REVIEW (sections 14, 38)
      Codex saying nothing, writing an empty file, or dying is never reported
      as "no issues found". read_review() raises instead, for the same reason
      unity_runner.verify_build() raises rather than returning a bool.

Never touches ~/.codex/auth.json - it is on the policy's secrets_never_touched
list. Login state is a HUMAN_GATE (initial_codex_login) and is reported, not
performed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from company.orchestrator.policy import Policy

# Verified subcommands, from the captured --help.
EXEC = "exec"
REVIEW = "review"
DOCTOR = "doctor"

# Read-only is the right default for a reviewer: it inspects the tree and
# reports, it does not edit it. The dangerously-bypass-* flags exist in this
# version and are deliberately never used.
SANDBOX_READ_ONLY = "read-only"

# Codex as a co-developer rather than a reviewer. Both values come from the
# captured --help ("[possible values: read-only, workspace-write,
# danger-full-access]"); danger-full-access is deliberately never used, and
# neither is --dangerously-bypass-approvals-and-sandbox. workspace-write
# confines edits to the repository, which is what makes the allowlist check in
# teamwork.py a second line of defence rather than the only one.
SANDBOX_WORKSPACE_WRITE = "workspace-write"

# The documented stand-in for "the prompt is on stdin", from the captured
# --help. Keeping the prompt off the command line is what makes a multi-line
# prompt survive cmd.exe on Windows - see exec_args.
STDIN_PROMPT = "-"

# The subscription is a quota, not a bill. Recognising exhaustion is what lets
# the caller degrade instead of escalating, so these patterns decide a state
# rather than merely colouring a message.
LIMIT_PATTERNS = (
    r"rate.?limit",
    r"quota",
    r"usage limit",
    r"too many requests",
    r"\b429\b",
)

# Only used to attach a hint to a failure. The raw output always travels with
# the exception - no failure is ever summarised away.
AUTH_PATTERNS = (
    r"not logged in",
    r"log ?in",
    r"unauthor",
    r"authenticat",
    r"\b401\b",
)


class CodexUnavailable(RuntimeError):
    """The CLI is missing or did not answer its own version probe."""


class CodexLimited(RuntimeError):
    """Subscription limit reached. Degrade to a fallback reviewer, do not spend."""


class ReviewNotRun(RuntimeError):
    """Section 38: no usable output, so this is not a passed review."""


class ReviewNotJson(RuntimeError):
    """A schema was requested but the final message was not valid JSON."""


@dataclass
class CodexResult:
    ok: bool
    exit_code: int | None
    last_message: str = ""
    stdout: str = ""
    stderr: str = ""
    command: list[str] = field(default_factory=list)
    output_path: Path | None = None
    detail: str = ""
    # Set when the output mentioned quota but the run still delivered.
    # The work is kept; the caller decides whether to slow down.
    limit_warning: str = ""


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(re.search(pattern, lowered) for pattern in patterns)


@dataclass
class CodexRunner:
    repo_root: Path
    policy: Policy
    binary: str = "codex"
    timeout_seconds: int = 900
    model: str | None = None
    # Injectable so command construction and the policy gates can be tested
    # without a signed-in Codex on the machine.
    runner: object = field(default=None, repr=False)

    # ---- locating the binary ---------------------------------------------

    @staticmethod
    def codex_path_from_profile(profile_path: Path) -> str | None:
        """The codex path detect-environment.ps1 already verified and recorded."""
        if not profile_path.is_file():
            return None
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            return None
        codex = (profile.get("tools") or {}).get("codex") or {}
        if codex.get("status") != "OK":
            return None
        return codex.get("path") or None

    @staticmethod
    def resolve_binary(profile_path: Path | None = None) -> str:
        """A path subprocess can actually launch.

        WHY THIS IS NOT JUST "codex". npm installs a global CLI on Windows as
        three shims side by side: an extension-less shell script, a .cmd and a
        .ps1. cmd.exe finds the .cmd because it applies PATHEXT - but
        subprocess uses CreateProcess, which does NOT, so it picks the
        extension-less shell script and dies with
        "[WinError 2] 지정된 파일을 찾을 수 없습니다". The same class of bug
        already bit detect-environment.ps1's Start-Process calls.

        So: prefer the path detect-environment.ps1 recorded (it resolved the
        launchable .cmd), then look for the .cmd explicitly, and only then
        fall back to the bare name for POSIX where it is correct.
        """
        if profile_path is not None:
            recorded = CodexRunner.codex_path_from_profile(profile_path)
            # Checked for existence: the profile is written on the build PC and
            # its Windows paths do not exist in a Linux container, where the
            # bare name below is the right answer.
            if recorded and Path(recorded).is_file():
                return recorded

        for candidate in ("codex.cmd", "codex.exe", "codex"):
            found = shutil.which(candidate)
            if found:
                return found

        # Nothing found. Returned rather than raised so is_available() can
        # report it as a status instead of a traceback.
        return "codex"

    # ---- environment -----------------------------------------------------

    def child_env(self, environ: dict[str, str] | None = None) -> dict[str, str]:
        """The subprocess environment, with billable keys removed.

        Section 7: OPENAI_API_KEY sitting in the environment is not permission
        to bill it. While allow_openai_api_billing is false the key is stripped
        so Codex cannot silently switch from the subscription to a paid path.
        """
        env = dict(os.environ if environ is None else environ)
        if self.policy.allows("allow_openai_api_billing"):
            return env
        for name in self.policy.blocked_env_keys:
            env.pop(name, None)
        return env

    def stripped_keys(self, environ: dict[str, str] | None = None) -> list[str]:
        """Names of blocked keys that were present and removed. Names only."""
        source = dict(os.environ if environ is None else environ)
        if self.policy.allows("allow_openai_api_billing"):
            return []
        return [name for name in self.policy.blocked_env_keys if source.get(name)]

    # ---- invocation building ---------------------------------------------

    def exec_args(self, *, output_file: Path,
                  schema_file: Path | None = None,
                  sandbox: str = SANDBOX_READ_ONLY,
                  json_events: bool = False,
                  subcommand: str | None = None) -> list[str]:
        """Build a `codex exec` command from verified flags only.

        THE PROMPT IS NOT HERE. It goes on stdin, and this ends with "-" to
        say so. The captured --help documents both: "If not provided as an
        argument (or if `-` is used), instructions are read from stdin."

        Why that matters rather than being a style choice: on Windows the
        resolved binary is codex.cmd, a BATCH FILE, so the invocation goes
        through cmd.exe's parser. A task prompt from teamwork.build_prompt is
        ~58 lines and contains "<Colour>" - cmd.exe would treat the newlines
        as command terminators and the angle brackets as redirections. stdin
        never touches that parser.

        Note also the absence of --ask-for-approval: `codex exec` is already
        non-interactive and does not accept it. --color never keeps ANSI escape
        codes out of captured output.
        """
        args = [self.binary, EXEC]
        if subcommand:
            args.append(subcommand)

        args += ["--cd", str(self.repo_root)]
        args += ["--sandbox", sandbox]
        args += ["--color", "never"]
        args += ["--output-last-message", str(output_file)]

        if schema_file is not None:
            args += ["--output-schema", str(schema_file)]
        if json_events:
            args.append("--json")
        if self.model:
            args += ["--model", self.model]

        # `codex exec [OPTIONS] [PROMPT]`, with "-" as the prompt meaning
        # "read it from stdin". Explicit rather than omitted, so the intent
        # does not depend on codex detecting that stdin happens to be a pipe.
        args.append(STDIN_PROMPT)
        return args

    # ---- execution -------------------------------------------------------

    def _run(self, args: list[str], timeout: int | None = None,
             stdin_text: str | None = None) -> tuple[int, str, str]:
        if self.runner is not None:  # test seam
            return self.runner(args, self.child_env(), stdin_text)

        completed = subprocess.run(
            args, capture_output=True, text=True,
            cwd=str(self.repo_root),
            env=self.child_env(),
            timeout=timeout or self.timeout_seconds,
            # The prompt, encoded with the same encoding named below. Passing
            # it here rather than in argv is what keeps a 58-line prompt out
            # of cmd.exe's parser on Windows.
            input=stdin_text,
            # Explicit, because text=True otherwise decodes with the machine's
            # locale encoding. On the Korean build PC that is cp949, and Codex
            # emits UTF-8 - which crashed `codex --doctor` outright with
            # "'cp949' codec can't decode byte 0xe2". replace, not strict: a
            # diagnostic pipe must survive one odd byte rather than take the
            # whole run down with it.
            encoding="utf-8", errors="replace",
        )
        return completed.returncode, completed.stdout, completed.stderr

    def is_available(self) -> tuple[bool, str]:
        """(usable, detail). Never raises - callers need a status, not a trace."""
        try:
            code, out, err = self._run([self.binary, "--version"], timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            # Naming the path that was tried is the whole difference between a
            # fixable report and a shrug: "codex" failing and
            # "C:\...\codex.cmd" failing mean different things.
            hint = ""
            if isinstance(exc, FileNotFoundError) or "WinError 2" in str(exc):
                hint = (" - nothing launchable at that path. On Windows the bare "
                        "name cannot work: npm's extension-less shim is not a Win32 "
                        "executable and subprocess does not apply PATHEXT. Run "
                        "AI_GAME_COMPANY/tools/detect-environment.ps1 so the .cmd "
                        "path is recorded in HARDWARE_PROFILE.json.")
            return False, f"codex --version could not run [tried: {self.binary}]{hint}: {exc}"
        if code != 0:
            return False, f"codex --version exited {code}: {(err or out).strip()[:200]}"
        return True, (out or err).strip()

    def doctor(self) -> CodexResult:
        """Raw `codex doctor` output. Deliberately not parsed.

        The probe captured this subcommand's existence, not its output format,
        so interpreting it would be the guesswork STEP 5 forbids. Login state
        is a HUMAN_GATE anyway - this exists so a human can read it.
        """
        try:
            code, out, err = self._run([self.binary, DOCTOR], timeout=120)
        except (OSError, subprocess.SubprocessError) as exc:
            raise CodexUnavailable(f"codex doctor could not run: {exc}") from exc
        return CodexResult(ok=(code == 0), exit_code=code, stdout=out, stderr=err,
                           command=[self.binary, DOCTOR])

    # ---- review ----------------------------------------------------------

    def _workspace(self) -> Path:
        path = self.repo_root / "AI_GAME_COMPANY" / "logs" / "codex-runs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def review(self, prompt: str, *, schema: dict[str, Any] | None = None,
               use_review_subcommand: bool = False,
               timeout_seconds: int | None = None) -> CodexResult:
        """Run one non-interactive review. Raises rather than faking a pass.

        The result is read from --output-last-message rather than scraped from
        stdout: stdout carries progress chatter, and a file either exists with
        content or it does not, which is the distinction section 38 turns on.
        """
        self.policy.require("use_codex_subscription", "Codex review")
        return self._exec(
            prompt, kind="review", sandbox=SANDBOX_READ_ONLY, schema=schema,
            subcommand=REVIEW if use_review_subcommand else None,
            timeout_seconds=timeout_seconds,
        )

    def implement(self, prompt: str, *, timeout_seconds: int | None = None) -> CodexResult:
        """Let Codex WRITE code, not just comment on it.

        This is the co-development path: Codex is handed a task from the shared
        board and edits the working tree itself, with --sandbox workspace-write
        so its edits cannot leave the repository.

        Two gates before it runs, because this one changes files:

          use_codex_subscription  the same subscription-only rule as review()
          allow_codex_write       a separate opt-in, so turning the reviewer on
                                  does not silently also grant write access

        What this deliberately does NOT do is decide whether the work was any
        good. The caller (teamwork.run_task) checks the diff against the task's
        file allowlist and runs the Unity pipeline; Codex exiting 0 only means
        it finished, never that the change is correct.
        """
        self.policy.require("use_codex_subscription", "Codex implementation")
        self.policy.require("allow_codex_write", "Codex writing to the working tree")
        return self._exec(
            prompt, kind="implement", sandbox=SANDBOX_WORKSPACE_WRITE,
            timeout_seconds=timeout_seconds,
        )

    def _exec(self, prompt: str, *, kind: str, sandbox: str,
              schema: dict[str, Any] | None = None,
              subcommand: str | None = None,
              timeout_seconds: int | None = None) -> CodexResult:
        """One non-interactive Codex run, with the section 38 rules applied.

        Shared by review() and implement() so the "a run that did not run is
        not a pass" handling cannot drift apart between the two.
        """
        available, detail = self.is_available()
        if not available:
            raise CodexUnavailable(detail)

        workspace = self._workspace()
        stamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        output_file = workspace / f"{kind}-{stamp}.txt"

        schema_file: Path | None = None
        if schema is not None:
            schema_file = workspace / f"schema-{stamp}.json"
            schema_file.write_text(json.dumps(schema, indent=2), encoding="utf-8")

        args = self.exec_args(
            output_file=output_file, schema_file=schema_file,
            sandbox=sandbox, subcommand=subcommand,
        )

        try:
            code, out, err = self._run(args, timeout=timeout_seconds,
                                       stdin_text=prompt)
        except subprocess.TimeoutExpired as exc:
            raise ReviewNotRun(
                f"codex exec ({kind}) timed out after "
                f"{timeout_seconds or self.timeout_seconds}s. A timeout is not a pass. "
                "On an implement run the working tree may hold a half-finished edit - "
                "check 'git status' before doing anything else."
            ) from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise CodexUnavailable(f"codex exec could not run: {exc}") from exc

        combined = f"{out}\n{err}"

        last_message = ""
        if output_file.is_file():
            last_message = output_file.read_text(encoding="utf-8", errors="replace").strip()

        # A limit MENTIONED is not a limit that stopped the work. This check
        # used to run before the output was even read, so a run that finished
        # the task and merely warned about quota was thrown away whole - which
        # is exactly what happened to CODEX-OFFICE1: Codex reported the task
        # complete with 46 tests passing, and the caller was told it failed.
        #
        # So the quota state now means what it says: the run produced nothing
        # usable AND said why. Degrade then; keep the work otherwise.
        mentions_limit = _matches(combined, LIMIT_PATTERNS)
        produced_result = code == 0 and bool(last_message)

        if mentions_limit and not produced_result:
            raise CodexLimited(
                "Codex subscription limit reached and the run produced nothing usable. "
                "Policy on_codex_limit forbids escalating to a paid API - fall back to "
                f"{self.policy.raw.get('on_codex_limit', {}).get('fallback_order')}. "
                f"Output: {combined.strip()[:300]}"
            )

        result = CodexResult(
            ok=(code == 0 and bool(last_message)),
            exit_code=code,
            last_message=last_message,
            stdout=out,
            stderr=err,
            command=args,
            output_path=output_file if output_file.is_file() else None,
            limit_warning=(combined.strip()[:300] if mentions_limit else ""),
        )

        if code != 0:
            hint = " (looks like a login problem - initial_codex_login is a HUMAN_GATE)" \
                if _matches(combined, AUTH_PATTERNS) else ""
            result.detail = f"codex exec ({kind}) exited {code}{hint}"
            raise ReviewNotRun(f"{result.detail}. Output: {combined.strip()[:500]}")

        if not last_message:
            # The dangerous case: exit 0 and nothing to show. Reporting that as
            # "no issues found" - or, on an implement run, as "task done" - is
            # exactly the section 38 failure.
            raise ReviewNotRun(
                f"codex exec ({kind}) exited 0 but wrote no final message to "
                f"{output_file}. An empty result is not a pass."
            )

        return result

    def review_json(self, prompt: str, schema: dict[str, Any],
                    **kwargs: Any) -> Any:
        """review() plus a parse. Raises if the model ignored the schema."""
        result = self.review(prompt, schema=schema, **kwargs)
        text = result.last_message

        # Models often wrap JSON in a fenced block even when given a schema.
        fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1)

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ReviewNotJson(
                f"--output-schema was supplied but the final message did not parse "
                f"as JSON ({exc}). Saved at {result.output_path}. Not treating "
                "unparseable output as an empty finding list."
            ) from exc

    def status_summary(self) -> str:
        available, detail = self.is_available()
        if not available:
            return f"Codex UNAVAILABLE - {detail}"

        lines = [f"Codex available - {detail}"]
        if not self.policy.allows("use_codex_subscription"):
            lines.append("  BLOCKED: policy use_codex_subscription is not true")
        lines.append(
            "  co-development (Codex writes code): "
            + ("ENABLED" if self.policy.allows("allow_codex_write")
               else "OFF - policy allow_codex_write is not true, so Codex can only review")
        )
        stripped = self.stripped_keys()
        if stripped:
            lines.append(
                "  billable keys present and stripped from the child environment: "
                + ", ".join(stripped)
            )
        lines.append(
            "  login state not checked here: ~/.codex/auth.json is on "
            "secrets_never_touched, and initial_codex_login is a HUMAN_GATE. "
            "Run 'codex doctor' to see it."
        )
        return "\n".join(lines)
