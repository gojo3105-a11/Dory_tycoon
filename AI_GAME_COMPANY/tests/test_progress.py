"""Tests for the Korean progress summariser.

Run:  python3 AI_GAME_COMPANY/tests/test_progress.py

The rule under test is the one that makes this module worth having: every
phrase it produces is anchored to a line the orchestrator actually printed.
So most of what follows is about what it says when it has NOTHING to go on -
because a status line that sounds confident on no evidence is exactly the
failure this project keeps writing rules against.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.orchestrator import progress as prog  # noqa: E402

HANDING = "=== HANDING CODEX-BOARD1 TO CODEX ===\n  Three bugs in the board runner\n"
WORKING = HANDING + "  allowlist: teamwork.py\n  running codex exec --sandbox workspace-write ...\n"


class PhaseTests(unittest.TestCase):
    def test_no_output_yet_is_starting_not_a_phase(self):
        # One second in, a process that has not printed is starting. Saying so
        # is true and less alarming than "확인 불가".
        summary = prog.summarise("team-run", "", 1.0)
        self.assertEqual(prog.STARTING, summary.phase)
        self.assertEqual("", summary.evidence)

    def test_unrecognisable_output_is_confirmed_unknown(self):
        summary = prog.summarise("team-run", "some line nobody planned for\n", 5.0)
        self.assertEqual(prog.UNKNOWN_PHASE, summary.phase)
        self.assertIn("확인 불가", summary.phase)
        # Still shows the line, so a reader can see what it could not read.
        self.assertEqual("some line nobody planned for", summary.evidence)

    def test_the_latest_marker_wins_because_a_run_moves_forward(self):
        summary = prog.summarise("team-run", WORKING, 60.0)
        self.assertEqual("Codex가 코드를 작성하는 중", summary.phase)

    def test_the_phase_carries_the_line_it_was_read_from(self):
        summary = prog.summarise("team-run", WORKING, 60.0)
        self.assertIn("running codex exec", summary.evidence)

    def test_an_earlier_marker_is_reported_before_a_later_one_appears(self):
        summary = prog.summarise("team-run", HANDING, 2.0)
        self.assertEqual("작업 명세를 읽고 Codex에게 넘기는 중", summary.phase)

    def test_a_refusal_reads_as_a_refusal(self):
        summary = prog.summarise(
            "team-run", HANDING + "REFUSED: task depends on X, which is not done yet.\n", 3.0)
        self.assertIn("거부", summary.phase)

    def test_a_quota_stop_is_named_rather_than_called_a_failure(self):
        summary = prog.summarise(
            "team-run", WORKING + "CODEX_LIMITED: subscription limit reached\n", 900.0)
        self.assertIn("Codex 사용 한도", summary.phase)

    def test_a_silent_phase_is_flagged_so_the_page_does_not_look_hung(self):
        # run_pipeline prints its step results only after Unity returns, so a
        # build genuinely shows nothing for a long time.
        summary = prog.summarise(
            "build", "=== LOCAL BUILD: game01 ===\n  This takes a while - Gradle\n", 400.0)
        self.assertTrue(summary.slow)

    def test_a_finished_run_reports_the_outcome_not_the_last_phase(self):
        ok = prog.summarise("team-run", WORKING, 60.0, done=True, exit_code=0)
        self.assertEqual("완료", ok.phase)
        bad = prog.summarise("team-run", WORKING, 60.0, done=True, exit_code=4)
        self.assertIn("실패", bad.phase)
        self.assertIn("4", bad.phase)
        self.assertFalse(bad.slow)

    def test_an_unknown_action_does_not_crash_and_admits_it(self):
        summary = prog.summarise("no-such-action", "hello\n", 1.0)
        self.assertEqual(prog.UNKNOWN_PHASE, summary.phase)
        self.assertEqual("no-such-action", summary.action_label)

    def test_a_trimmed_head_does_not_produce_a_stale_phase(self):
        # The job keeps only a tail once a log grows. A marker scrolled out of
        # that tail must not still be reported as the current phase.
        long_tail = "x\n" * 20000
        summary = prog.summarise("team-run", HANDING + long_tail, 60.0)
        self.assertEqual(prog.UNKNOWN_PHASE, summary.phase)

    def test_every_build_step_has_both_an_ok_and_a_fail_marker(self):
        # A pipeline that can only report success is the failure mode this
        # project has a rule against, so pin the pairing.
        phrases = [m.pattern.pattern for m in prog.MARKERS["build"]]
        for step in ("generate", "validate", "build"):
            self.assertTrue(any(f"OK \\] {step}" in p for p in phrases), step)
            self.assertTrue(any(f"FAIL\\] {step}" in p for p in phrases), step)


class ElapsedTests(unittest.TestCase):
    def test_reads_as_korean_at_each_scale(self):
        self.assertEqual("0초", prog.elapsed_korean(0))
        self.assertEqual("59초", prog.elapsed_korean(59.9))
        self.assertEqual("1분 0초", prog.elapsed_korean(60))
        self.assertEqual("2분 5초", prog.elapsed_korean(125))
        self.assertEqual("1시간 5분", prog.elapsed_korean(3900))

    def test_a_negative_reading_is_clamped_rather_than_printed(self):
        self.assertEqual("0초", prog.elapsed_korean(-3))


class NoInventedNumbersTests(unittest.TestCase):
    def test_nothing_here_reports_a_percentage(self):
        # There is no denominator anywhere in this pipeline: no step count, no
        # token count, no ETA. A percentage could only be made up.
        source = (Path(prog.__file__)).read_text(encoding="utf-8")
        rendered = "\n".join(
            prog.summarise(action, WORKING, 90.0).phase
            for action in prog.MARKERS)
        self.assertNotIn("%", rendered)
        self.assertNotIn("퍼센트", source)

    def test_agent_prefix_is_empty_for_an_action_that_drives_no_ai(self):
        self.assertEqual("Codex", prog.agent_prefix_for("team-run"))
        self.assertEqual("", prog.agent_prefix_for("git-status"))
        self.assertEqual("", prog.agent_prefix_for("dashboard"))

    def test_every_action_the_server_can_run_has_a_korean_label(self):
        from company.orchestrator import server

        for name in server.ACTIONS:
            self.assertIn(name, prog.ACTION_LABEL, name)
            self.assertTrue(re.search(r"[가-힣]", prog.ACTION_LABEL[name]), name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
