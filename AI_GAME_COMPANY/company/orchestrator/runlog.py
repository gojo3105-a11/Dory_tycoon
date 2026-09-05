"""Every orchestrator run leaves a committed record, so failures reach Claude.

Unity compile errors and build results already travel this way: a script on
the PC writes Reports/errors/latest.txt and Reports/build-status/latest.txt,
the scheduled sync commits them, and Claude reads them straight from the
fork. Orchestrator runs had no such channel - when `team run` failed, the
output died on the PC console and a person had to retype it into a chat
window. Three separate bugs on 2026-09-02 were diagnosed that way, each one
obvious the moment its output was pasted.

This applies the pattern that already works, with two rules that matter more
than the feature:

  NO SECRET VALUE IS EVER WRITTEN. The value of any env var named in policy
  blocked_env_keys, or by gemini_api_key_env, is replaced before the file is
  written. Names may appear; values never - the same "names only" idiom as
  CodexRunner.stripped_keys.

  LOGGING NEVER CHANGES THE OUTCOME. If the record cannot be written - a
  read-only disk, a missing directory, anything - the command still returns
  its real exit code and the failure to log goes to stderr and nowhere else.
  A logging bug that turned a passing build into a failure would be worse
  than the problem this file solves.

Every entry records failures as loudly as successes; a log with only
successes in it is worse than none.
"""

from __future__ import annotations

import io
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, TextIO

REPORT_TITLE = "# Orchestrator run report"
LATEST_NAME = "latest.txt"
# Committed to git, so unbounded growth is a repository problem, not just a
# disk one. Oldest beyond this are deleted.
MAX_ENTRIES = 50
# The tail that goes into the file. A Unity build log must not land in git.
MAX_TAIL_CHARS = 12_000
# Kept in memory while the command runs; larger than the tail so the redaction
# below sees a bit of context, but still bounded.
MAX_BUFFER_CHARS = 64_000
# A value shorter than this is not treated as a secret to scrub - "1" or "ok"
# would otherwise be redacted out of every line that contains it.
MIN_SECRET_LENGTH = 8

# Nothing is skipped. `serve` was excluded here at first because it runs for
# hours and ends only at Ctrl+C - but a serve that DIES AT STARTUP is exactly
# the failure worth having on record, and excluding it meant the one command
# the user reported as broken left no trace at all. Its record is written when
# it exits, and both the buffer and the written tail are bounded, so a long
# healthy session costs nothing. Kept as a constant so the mechanism is still
# there if a command ever genuinely should not be recorded.
SKIP_COMMANDS: tuple[str, ...] = ()


class _Tee(io.TextIOBase):
    """Writes through to the real stream and keeps a bounded copy."""

    def __init__(self, real: TextIO, sink: list[str], budget: list[int]):
        self._real = real
        self._sink = sink
        self._budget = budget

    def write(self, text: str) -> int:  # type: ignore[override]
        try:
            written = self._real.write(text)
        except UnicodeEncodeError:
            # A cp949 console cannot show an em dash. Degrade the glyph on
            # the terminal, keep the exact text in the record, keep running.
            encoding = getattr(self._real, "encoding", None) or "ascii"
            safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
            written = self._real.write(safe)
        self._sink.append(text)
        self._budget[0] += len(text)
        if self._budget[0] > MAX_BUFFER_CHARS:
            joined = "".join(self._sink)[-MAX_BUFFER_CHARS:]
            self._sink[:] = [joined]
            self._budget[0] = len(joined)
        return written

    def flush(self) -> None:
        self._real.flush()

    # The real stream's identity matters to code that checks isatty() to
    # decide on colour; answer for it rather than for this wrapper.
    def isatty(self) -> bool:
        try:
            return self._real.isatty()
        except (AttributeError, ValueError):
            return False

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return getattr(self._real, "encoding", "utf-8")

    def fileno(self) -> int:
        return self._real.fileno()


def redact(text: str, environ: dict[str, str], names: Iterable[str]) -> str:
    """Replace the VALUE of every named env var with a marker carrying its NAME."""
    for name in names:
        value = environ.get(name, "")
        if len(value) < MIN_SECRET_LENGTH:
            continue
        text = text.replace(value, f"[REDACTED:{name}]")
    return text


def duration_korean(seconds: float) -> str:
    total = max(0, int(seconds))
    if total < 60:
        return f"{total}초"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}분 {secs}초"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}시간 {minutes}분"


@dataclass
class RunRecord:
    command: str
    argv: list[str]
    started: datetime
    exit_code: int | None = None
    error: str = ""
    seconds: float = 0.0
    output: str = ""

    @property
    def outcome(self) -> str:
        if self.error:
            return "RAISED"
        if self.exit_code == 0:
            return "OK"
        if self.exit_code is None:
            return "UNKNOWN"
        return "FAILED"

    def render(self) -> str:
        argv = " ".join(self.argv)
        lines = [
            REPORT_TITLE,
            "",
            f"Generated: {self.started.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Command: {argv or self.command}",
            f"Outcome: {self.outcome}",
            f"Exit: {self.exit_code if self.exit_code is not None else '-'}",
            f"Duration: {duration_korean(self.seconds)}",
        ]
        if self.error:
            lines += ["", "## Exception", "", self.error.rstrip()]
        tail = self.output[-MAX_TAIL_CHARS:]
        if len(self.output) > MAX_TAIL_CHARS:
            tail = "...(앞부분 생략)...\n" + tail
        lines += ["", "## Output (tail)", "", tail.rstrip() or "(no output)", ""]
        return "\n".join(lines)


@dataclass
class Recorder:
    """Records one command's run into <directory>/ and <directory>/latest.txt."""
    directory: Path
    redact_names: list[str] = field(default_factory=list)
    environ: dict[str, str] | None = None
    max_entries: int = MAX_ENTRIES

    def should_record(self, command: str) -> bool:
        return command not in SKIP_COMMANDS

    def write(self, record: RunRecord) -> Path | None:
        """Write the record. Returns the path, or None when it could not.

        Never raises: the caller is the CLI's exit path, and a logging failure
        must not become the command's failure. The reason goes to stderr.
        """
        try:
            environ = os.environ if self.environ is None else self.environ
            record.output = redact(record.output, dict(environ), self.redact_names)
            record.error = redact(record.error, dict(environ), self.redact_names)

            self.directory.mkdir(parents=True, exist_ok=True)
            stamp = record.started.strftime("%Y%m%d-%H%M%S")
            slug = re.sub(r"[^A-Za-z0-9]+", "-", record.command).strip("-") or "run"
            text = record.render()
            entry = self.directory / f"{stamp}-{slug}.txt"
            entry.write_text(text, encoding="utf-8")
            (self.directory / LATEST_NAME).write_text(text, encoding="utf-8")
            self._prune()
            return entry
        except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
            # sys.stderr, not sys.__stderr__: by the time write() runs the
            # tee has been removed, so this is the real stream - and a test
            # that redirects stderr can see it.
            try:
                print(f"(run log not written: {type(exc).__name__}: {exc})",
                      file=sys.stderr)
            except Exception:  # noqa: BLE001
                pass
            return None

    def _prune(self) -> None:
        entries = sorted(p for p in self.directory.glob("*.txt") if p.name != LATEST_NAME)
        for stale in entries[:-self.max_entries] if len(entries) > self.max_entries else []:
            try:
                stale.unlink()
            except OSError:
                pass

    def run(self, command: str, argv: list[str], func: Any) -> int:
        """Call func() with stdout/stderr captured, then record the outcome.

        The return value and any exception are passed through untouched -
        this only observes. func's own prints still reach the terminal.
        """
        if not self.should_record(command):
            return func()

        sink: list[str] = []
        budget = [0]
        started = datetime.now()
        clock = time.monotonic()
        real_out, real_err = sys.stdout, sys.stderr
        sys.stdout = _Tee(real_out, sink, budget)  # type: ignore[assignment]
        sys.stderr = _Tee(real_err, sink, budget)  # type: ignore[assignment]

        record = RunRecord(command=command, argv=argv, started=started)
        try:
            code = func()
            record.exit_code = int(code) if code is not None else 0
            return record.exit_code
        except SystemExit as exc:
            code = exc.code
            record.exit_code = code if isinstance(code, int) else (0 if code is None else 1)
            raise
        except KeyboardInterrupt:
            record.error = "KeyboardInterrupt: stopped by the user"
            record.exit_code = 130
            raise
        except BaseException as exc:
            record.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            record.exit_code = 1
            raise
        finally:
            sys.stdout, sys.stderr = real_out, real_err
            record.seconds = time.monotonic() - clock
            record.output = "".join(sink)
            self.write(record)


def parse_latest(text: str) -> dict[str, str]:
    """The header fields of a report, for the dashboard. Missing keys absent."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("## "):
            break
        match = re.match(r"^([A-Za-z-]+):\s*(.*)$", line)
        if match:
            fields[match.group(1)] = match.group(2).strip()
    return fields
