"""Tests for the orchestrator run log.

Run:  python3 AI_GAME_COMPANY/tests/test_runlog.py

Two rules outrank the feature, and most of these exist for them: no secret
value may ever be written, and a failure to log may never change a command's
exit code.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.orchestrator import runlog  # noqa: E402

SECRET = "sk-live-0123456789abcdef"


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "runs"
        self.recorder = runlog.Recorder(self.dir, redact_names=["OPENAI_API_KEY"],
                                        environ={"OPENAI_API_KEY": SECRET})

    def tearDown(self):
        self.tmp.cleanup()

    def run_quietly(self, command, func, argv=None):
        # The tee writes through to the real stdout; keep the test output clean.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return self.recorder.run(command, argv or [command], func)

    def latest(self):
        return (self.dir / "latest.txt").read_text(encoding="utf-8")

    def test_a_successful_run_writes_an_entry_and_latest(self):
        def ok():
            print("=== HANDING X TO CODEX ===")
            return 0

        code = self.run_quietly("team", ok, ["team", "run", "--task", "X"])
        self.assertEqual(0, code)
        text = self.latest()
        self.assertIn("Outcome: OK", text)
        self.assertIn("Command: team run --task X", text)
        self.assertIn("=== HANDING X TO CODEX ===", text)
        self.assertEqual(1, len([p for p in self.dir.glob("*.txt") if p.name != "latest.txt"]))

    def test_a_non_zero_run_is_recorded_as_a_failure(self):
        def bad():
            print("REFUSED: no")
            return 2

        self.assertEqual(2, self.run_quietly("team", bad))
        text = self.latest()
        self.assertIn("Outcome: FAILED", text)
        self.assertIn("Exit: 2", text)
        self.assertIn("REFUSED: no", text)

    def test_a_raising_run_names_the_exception_and_re_raises(self):
        def boom():
            raise RuntimeError("codex exploded")

        with self.assertRaises(RuntimeError):
            self.run_quietly("team", boom)
        text = self.latest()
        self.assertIn("Outcome: RAISED", text)
        self.assertIn("RuntimeError: codex exploded", text)

    def test_stderr_is_captured_too(self):
        def noisy():
            print("to stderr", file=sys.stderr)
            return 0

        self.run_quietly("build", noisy)
        self.assertIn("to stderr", self.latest())

    def test_a_secret_value_never_reaches_the_file(self):
        def leaky():
            print(f"Authorization: Bearer {SECRET}")
            print(f"env dump OPENAI_API_KEY={SECRET}")
            return 0

        self.run_quietly("codex", leaky)
        text = self.latest()
        self.assertNotIn(SECRET, text)
        self.assertIn("[REDACTED:OPENAI_API_KEY]", text)
        # The exception path is scrubbed as well, not only stdout.

        def leaky_raise():
            raise RuntimeError(f"bad key {SECRET}")

        with self.assertRaises(RuntimeError):
            self.run_quietly("codex", leaky_raise)
        self.assertNotIn(SECRET, self.latest())

    def test_a_short_value_is_not_treated_as_a_secret(self):
        # Redacting "1" would scrub every line containing a 1.
        recorder = runlog.Recorder(self.dir, redact_names=["K"], environ={"K": "1"})
        with redirect_stdout(io.StringIO()):
            recorder.run("x", ["x"], lambda: (print("step 1 of 1"), 0)[1])
        self.assertIn("step 1 of 1", self.latest())

    def test_the_directory_is_capped_oldest_first(self):
        recorder = runlog.Recorder(self.dir, max_entries=3, environ={})
        from datetime import datetime, timedelta
        base = datetime(2026, 9, 3, 10, 0, 0)
        for i in range(5):
            record = runlog.RunRecord(command="x", argv=["x"],
                                      started=base + timedelta(minutes=i),
                                      exit_code=0, output=f"run {i}")
            recorder.write(record)
        entries = sorted(p.name for p in self.dir.glob("*.txt") if p.name != "latest.txt")
        self.assertEqual(3, len(entries))
        self.assertTrue(entries[0].startswith("20260903-100200"), entries)
        self.assertIn("run 4", self.latest())

    def test_a_write_failure_does_not_change_the_exit_code(self):
        # A file where the directory should be: mkdir fails, write fails.
        blocked = Path(self.tmp.name) / "blocked"
        blocked.write_text("not a directory", encoding="utf-8")
        recorder = runlog.Recorder(blocked, environ={})

        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = recorder.run("team", ["team"], lambda: 0)
        self.assertEqual(0, code)

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = recorder.run("team", ["team"], lambda: 3)
        self.assertEqual(3, code)

    def test_serve_is_not_recorded(self):
        calls = []
        self.run_quietly("serve", lambda: calls.append(1) or 0)
        self.assertEqual([1], calls)
        self.assertFalse(self.dir.exists())

    def test_the_output_tail_is_bounded(self):
        def chatty():
            for i in range(20000):
                print(f"line {i}")
            return 0

        self.run_quietly("build", chatty)
        text = self.latest()
        self.assertLess(len(text), runlog.MAX_TAIL_CHARS + 600)
        self.assertIn("line 19999", text)
        self.assertIn("앞부분 생략", text)

    def test_stdout_is_restored_afterwards(self):
        before_out, before_err = sys.stdout, sys.stderr
        self.run_quietly("team", lambda: 0)
        self.assertIs(before_out, sys.stdout)
        self.assertIs(before_err, sys.stderr)


class ConsoleEncodingTests(unittest.TestCase):
    """The cp949 case: a Korean Windows console raised UnicodeEncodeError while
    PRINTING a finished run's summary, and a 215-second Codex run's report
    died with it. The tee must degrade the glyph on screen and keep going."""

    class Cp949Console(io.TextIOBase):
        encoding = "cp949"

        def __init__(self):
            self.shown = []

        def write(self, text):
            text.encode("cp949")          # raises on an em dash, like the real console
            self.shown.append(text)
            return len(text)

    def test_an_unencodable_glyph_is_degraded_on_screen_and_kept_in_the_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = runlog.Recorder(Path(tmp), environ={})
            console = self.Cp949Console()
            real_out = sys.stdout
            sys.stdout = console
            try:
                code = recorder.run("team", ["team"], lambda: (print("codex said \u2014 done"), 0)[1])
            finally:
                sys.stdout = real_out
            self.assertEqual(0, code)
            self.assertTrue(any("codex said ? done" in t for t in console.shown), console.shown)
            latest = (Path(tmp) / "latest.txt").read_text(encoding="utf-8")
            self.assertIn("codex said \u2014 done", latest)


class ParseTests(unittest.TestCase):
    def test_reads_the_header_and_stops_at_the_body(self):
        text = ("# Orchestrator run report\n\nGenerated: 2026-09-03 10:00:00\n"
                "Command: team run --task X\nOutcome: FAILED\nExit: 4\nDuration: 12분 3초\n"
                "\n## Output (tail)\n\nExit: 99 (this is body text)\n")
        fields = runlog.parse_latest(text)
        self.assertEqual("FAILED", fields["Outcome"])
        self.assertEqual("4", fields["Exit"])
        self.assertEqual("team run --task X", fields["Command"])

    def test_no_percentage_anywhere(self):
        source = Path(runlog.__file__).read_text(encoding="utf-8")
        self.assertNotIn("%)", source.replace("%Y", "").replace("%m", "").replace("%d", "")
                         .replace("%H", "").replace("%M", "").replace("%S", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
