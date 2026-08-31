"""Tests for the Unity batch runner.

Run:  python3 AI_GAME_COMPANY/tests/test_unity_runner.py

Unity itself cannot run here, so these cover the two things that CAN be
verified without it and that would bite hardest if wrong:

  1. the generated invocation matches the workflow that actually built an APK
     (section 38: not invented, and any drift means the orchestrator is
     running a command nobody has ever proven works)
  2. the build verification refuses to pass when any of section 32's three
     conditions is missing - especially "no APK on disk"

The subprocess call is injected, so no Windows and no Unity is required.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.orchestrator.policy import Policy, PolicyViolation  # noqa: E402
from company.orchestrator.unity_runner import (  # noqa: E402
    ENTRY_BUILD, ENTRY_GENERATE, ENTRY_VALIDATE, UnityResult, UnityRunner, ps_quote,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "game-factory.yml"
REAL_POLICY = REPO_ROOT / "AI_GAME_COMPANY" / "config" / "company_policy.json"


class FakeRunner:
    """Captures the generated script instead of executing PowerShell."""

    def __init__(self, exit_code: int = 0):
        self.exit_code = exit_code
        self.scripts: list[str] = []

    def __call__(self, script_path: Path, script_text: str):
        self.scripts.append(script_text)
        return self.exit_code, "", ""


class QuotingTests(unittest.TestCase):
    def test_spaces_survive_quoting(self):
        self.assertEqual(
            ps_quote(r"C:\Program Files\Unity\Editor\Unity.exe"),
            r"'C:\Program Files\Unity\Editor\Unity.exe'",
        )

    def test_single_quote_is_doubled(self):
        # An unescaped quote here would terminate the literal early and change
        # which command PowerShell runs.
        self.assertEqual(ps_quote("it's"), "'it''s'")


class InvocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fake = FakeRunner()
        self.runner = UnityRunner(
            repo_root=self.root, policy=Policy.load(REAL_POLICY), runner=self.fake
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_generate_matches_workflow_shape(self):
        args = self.runner.unity_args(ENTRY_GENERATE, "unity-generate",
                                      ["-gameSpec", "GameSpecs/game01.json"])
        self.assertEqual(args[:2], ["-batchmode", "-nographics"])
        self.assertIn("-projectPath", args)
        self.assertIn(ENTRY_GENERATE, args)
        self.assertIn("GameSpecs/game01.json", args)
        # -logFile last, as in the workflow, so a truncated arg list is obvious
        self.assertEqual(args[-2], "-logFile")

    def test_wrapper_goes_through_wait_for_unity(self):
        self.runner.generate("game01")
        script = self.fake.scripts[0]
        self.assertIn("wait-for-unity.ps1", script)
        self.assertIn("-SentinelName 'generate'", script)
        self.assertIn("-UnityArgs @(", script)
        # Calling Unity.exe directly is the bug this design exists to avoid.
        self.assertNotIn("Unity.exe", script)

    def test_build_gets_the_longer_timeout(self):
        self.runner.build_android("game01")
        self.assertIn("-TimeoutMinutes 60", self.fake.scripts[0])

    def test_generated_script_is_ascii(self):
        # PowerShell 5.1 reads a BOM-less UTF-8 .ps1 in the local codepage.
        self.runner.generate("game01")
        self.fake.scripts[0].encode("ascii")

    def test_entry_points_exist_in_the_working_workflow(self):
        """The proof that these method names are verified, not remembered."""
        if not WORKFLOW.is_file():
            self.skipTest("workflow not present")
        text = WORKFLOW.read_text(encoding="utf-8")
        for entry in (ENTRY_GENERATE, ENTRY_VALIDATE, ENTRY_BUILD):
            self.assertIn(entry, text, f"{entry} is not in the workflow that builds APKs")

    def test_pipeline_stops_at_first_failure(self):
        failing = UnityRunner(repo_root=self.root, policy=Policy.load(REAL_POLICY),
                              runner=FakeRunner(exit_code=1))
        results, apk = failing.run_pipeline("game01")
        self.assertEqual(len(results), 1)          # generate only
        self.assertEqual(results[0].step, "generate")
        self.assertIsNone(apk)


class BuildVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.policy = Policy.load(REAL_POLICY)
        self.runner = UnityRunner(repo_root=self.root, policy=self.policy,
                                  runner=FakeRunner())
        (self.root / "Logs").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_report(self):
        (self.root / "Logs" / "unity-build.log").write_text("build log", encoding="utf-8")

    def _write_apk(self, size: int = 1024):
        apk_dir = self.root / "Builds" / "game01" / "APK"
        apk_dir.mkdir(parents=True, exist_ok=True)
        apk = apk_dir / "Game01.apk"
        apk.write_bytes(b"x" * size)
        return apk

    def test_all_three_present_passes(self):
        self._write_report()
        expected = self._write_apk()
        got = self.runner.verify_build("game01", UnityResult("build", 0, True))
        self.assertEqual(got, expected)

    def test_zero_exit_but_no_apk_is_a_failure(self):
        # The exact thing section 38 forbids: reporting success with no APK.
        self._write_report()
        with self.assertRaises(PolicyViolation) as ctx:
            self.runner.verify_build("game01", UnityResult("build", 0, True))
        self.assertIn("apk file on disk", str(ctx.exception))

    def test_empty_apk_does_not_count(self):
        self._write_report()
        self._write_apk(size=0)
        with self.assertRaises(PolicyViolation):
            self.runner.verify_build("game01", UnityResult("build", 0, True))

    def test_apk_present_but_nonzero_exit_is_a_failure(self):
        self._write_report()
        self._write_apk()
        with self.assertRaises(PolicyViolation) as ctx:
            self.runner.verify_build("game01", UnityResult("build", 1, False))
        self.assertIn("process exit code", str(ctx.exception))

    def test_missing_build_report_is_a_failure(self):
        self._write_apk()
        with self.assertRaises(PolicyViolation) as ctx:
            self.runner.verify_build("game01", UnityResult("build", 0, True))
        self.assertIn("unity build report", str(ctx.exception))

    def test_find_apk_picks_the_newest(self):
        import os
        self._write_report()
        older = self._write_apk()
        newer_dir = self.root / "Builds" / "game01" / "AAB"
        newer_dir.mkdir(parents=True)
        newer = newer_dir / "Game01.aab"
        newer.write_bytes(b"y" * 64)
        os.utime(older, (1, 1))
        self.assertEqual(self.runner.find_apk("game01"), newer)

    def test_pipeline_reports_failure_when_apk_absent(self):
        self._write_report()
        results, apk = self.runner.run_pipeline("game01")
        self.assertIsNone(apk)
        build = [r for r in results if r.step == "build"][0]
        self.assertFalse(build.ok)
        self.assertIn("BUILD_FAILED", build.detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
