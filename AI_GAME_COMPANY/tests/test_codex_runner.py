"""Tests for the Codex review adapter.

Run:  python3 AI_GAME_COMPANY/tests/test_codex_runner.py

No Codex binary is needed: the runner is injected. What these check is that
the command is built only from flags the probe actually captured, that the
cost guards hold, and - most of all - that a review which did not really run
can never be reported as a clean one.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.orchestrator.codex_runner import (  # noqa: E402
    CodexLimited, CodexRunner, CodexUnavailable, ReviewNotJson, ReviewNotRun,
)
from company.orchestrator.policy import Policy, PolicyViolation  # noqa: E402

PROBE = Path(__file__).resolve().parents[1] / "config" / "cli-probes" / "codex.txt"

SCHEMA = {"type": "object", "properties": {"findings": {"type": "array"}}}


class FakeCodex:
    """Answers a codex invocation, and can write the output file like the real one."""

    def __init__(self, exit_code: int = 0, stdout: str = "", stderr: str = "",
                 writes: str | None = "no issues found"):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.writes = writes
        self.calls: list[list[str]] = []
        self.envs: list[dict] = []
        self.stdins: list[str | None] = []

    def __call__(self, args, env, stdin_text=None):
        self.calls.append(args)
        self.envs.append(env)
        self.stdins.append(stdin_text)

        if "--version" in args:
            return 0, "codex-cli 0.151.0", ""

        if self.writes is not None and "--output-last-message" in args:
            target = Path(args[args.index("--output-last-message") + 1])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.writes, encoding="utf-8")

        return self.exit_code, self.stdout, self.stderr


def policy_with(**overrides) -> Policy:
    raw = {
        "use_codex_subscription": True,
        "allow_openai_api_billing": False,
        "blocked_env_keys": ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
        "on_codex_limit": {"fallback_order": ["local_ai_review"]},
    }
    raw.update(overrides)
    return Policy(raw=raw)


class RunnerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, fake: FakeCodex, policy: Policy | None = None) -> CodexRunner:
        return CodexRunner(repo_root=self.root, policy=policy or policy_with(),
                           runner=fake)


class CommandBuildingTests(RunnerTestCase):
    """Only flags present in the captured probe may be used."""

    def test_uses_only_flags_the_probe_captured(self):
        if not PROBE.is_file():
            self.skipTest("no codex probe committed")
        probe_text = PROBE.read_text(encoding="utf-8-sig")
        exec_section = probe_text.split("### codex exec --help", 1)[-1]

        fake = FakeCodex()
        runner = self.make(fake)
        runner.review("check this")

        args = [a for a in fake.calls[-1] if a.startswith("--")]
        for flag in args:
            self.assertIn(flag, exec_section,
                          f"{flag} is not in the captured codex exec --help")

    def test_does_not_pass_ask_for_approval(self):
        # It exists on top-level `codex` but NOT on `codex exec`. Passing it
        # would fail every run - the reason STEP 5 requires a real probe.
        fake = FakeCodex()
        self.make(fake).review("hi")
        self.assertNotIn("--ask-for-approval", fake.calls[-1])
        self.assertNotIn("-a", fake.calls[-1])

    def test_defaults_to_a_read_only_sandbox(self):
        fake = FakeCodex()
        self.make(fake).review("hi")
        args = fake.calls[-1]
        self.assertEqual(args[args.index("--sandbox") + 1], "read-only")

    def test_never_uses_a_dangerous_bypass_flag(self):
        fake = FakeCodex()
        self.make(fake).review("hi")
        self.assertFalse([a for a in fake.calls[-1] if "dangerously" in a])

    def test_the_prompt_goes_on_stdin_not_the_command_line(self):
        # On Windows the resolved binary is codex.cmd, a batch file, so argv
        # is parsed by cmd.exe. A task prompt is ~58 lines and can contain
        # "<Colour>": cmd.exe would end the command at the first newline and
        # treat the angle brackets as redirection. The captured --help
        # documents "-" as "read the prompt from stdin", which skips that
        # parser entirely.
        fake = FakeCodex()
        self.make(fake).review("review the diff")

        self.assertEqual("-", fake.calls[-1][-1])
        self.assertNotIn("review the diff", fake.calls[-1])
        self.assertEqual("review the diff", fake.stdins[-1])

    def test_a_multiline_prompt_with_shell_metacharacters_stays_off_argv(self):
        # The concrete shape that breaks: newlines plus redirection
        # characters, exactly as build_prompt emits them.
        prompt = "line one\nPNG/<Colour>/Default/button.png\n100%% & done ^caret"
        fake = FakeCodex()
        self.make(fake).review(prompt)

        joined = " ".join(fake.calls[-1])
        for danger in ("\n", "<", ">", "&", "^"):
            self.assertNotIn(danger, joined,
                             f"{danger!r} reached the command line")
        self.assertEqual(prompt, fake.stdins[-1])

    def test_probe_documents_reading_the_prompt_from_stdin(self):
        # STEP 5: the behaviour relied on has to be in the captured help, not
        # assumed. If a future codex drops it, this fails instead of the run.
        if not PROBE.is_file():
            self.skipTest("no codex probe committed")
        exec_help = PROBE.read_text(encoding="utf-8-sig").split(
            "### codex exec --help", 1)[-1]
        self.assertIn("read from stdin", exec_help)

    def test_version_and_doctor_send_no_stdin(self):
        fake = FakeCodex()
        runner = self.make(fake)
        runner.is_available()
        self.assertIsNone(fake.stdins[-1])
        runner.doctor()
        self.assertIsNone(fake.stdins[-1])

    def test_review_subcommand_is_opt_in(self):
        fake = FakeCodex()
        runner = self.make(fake)
        runner.review("hi")
        self.assertNotIn("review", fake.calls[-1])
        runner.review("hi", use_review_subcommand=True)
        self.assertEqual(fake.calls[-1][1:3], ["exec", "review"])

    def test_schema_file_is_written_and_passed(self):
        fake = FakeCodex(writes='{"findings": []}')
        runner = self.make(fake)
        runner.review("hi", schema=SCHEMA)
        args = fake.calls[-1]
        schema_path = Path(args[args.index("--output-schema") + 1])
        self.assertTrue(schema_path.is_file())
        self.assertEqual(json.loads(schema_path.read_text())["type"], "object")


class CostGuardTests(RunnerTestCase):
    def test_blocked_api_keys_are_stripped_from_the_child_env(self):
        # Section 7: the key being present is not permission to bill it.
        fake = FakeCodex()
        runner = self.make(fake)
        env = runner.child_env({"OPENAI_API_KEY": "sk-real", "PATH": "/usr/bin"})
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertEqual(env["PATH"], "/usr/bin")

    def test_keys_survive_only_when_billing_is_explicitly_allowed(self):
        runner = self.make(FakeCodex(), policy_with(allow_openai_api_billing=True))
        env = runner.child_env({"OPENAI_API_KEY": "sk-real"})
        self.assertEqual(env["OPENAI_API_KEY"], "sk-real")

    def test_stripped_keys_reports_names_only(self):
        runner = self.make(FakeCodex())
        names = runner.stripped_keys({"OPENAI_API_KEY": "sk-secret-value"})
        self.assertEqual(names, ["OPENAI_API_KEY"])
        self.assertNotIn("sk-secret-value", " ".join(names))

    def test_review_is_blocked_when_the_subscription_is_not_allowed(self):
        runner = self.make(FakeCodex(), policy_with(use_codex_subscription=False))
        with self.assertRaises(PolicyViolation):
            runner.review("hi")

    def test_a_blocked_policy_sends_no_command_at_all(self):
        fake = FakeCodex()
        runner = self.make(fake, policy_with(use_codex_subscription=False))
        with self.assertRaises(PolicyViolation):
            runner.review("hi")
        self.assertEqual(fake.calls, [])

    def test_a_limit_warning_does_not_discard_finished_work(self):
        # What actually happened to CODEX-OFFICE1: Codex reported the task
        # complete with 46 tests passing, mentioned quota in passing, and the
        # whole result was thrown away as a failure. A limit MENTIONED is not
        # a limit that stopped the work.
        fake = FakeCodex(exit_code=0, stderr="warning: approaching rate limit",
                         writes="TASK CODEX-OFFICE1 is complete. 46 tests pass.")
        result = self.make(fake).review("hi")

        self.assertTrue(result.ok)
        self.assertIn("complete", result.last_message)
        # The warning is kept, not swallowed - the caller may want to slow down.
        self.assertIn("rate limit", result.limit_warning)

    def test_a_clean_run_carries_no_limit_warning(self):
        result = self.make(FakeCodex()).review("hi")
        self.assertEqual("", result.limit_warning)

    def test_quota_exhaustion_degrades_instead_of_escalating(self):
        fake = FakeCodex(exit_code=1, stderr="Error: usage limit reached (429)",
                         writes=None)
        with self.assertRaises(CodexLimited) as ctx:
            self.make(fake).review("hi")
        self.assertIn("local_ai_review", str(ctx.exception))
        self.assertIn("forbids escalating", str(ctx.exception))


class BinaryResolutionTests(RunnerTestCase):
    """Locating codex. This is what broke on the build PC."""

    def profile(self, **codex) -> Path:
        path = self.root / "HARDWARE_PROFILE.json"
        path.write_text(json.dumps({"tools": {"codex": codex}}), encoding="utf-8")
        return path

    def test_prefers_the_recorded_path_when_it_exists(self):
        shim = self.root / "codex.cmd"
        shim.write_text("@echo off", encoding="utf-8")
        resolved = CodexRunner.resolve_binary(
            self.profile(status="OK", path=str(shim)))
        self.assertEqual(str(shim), resolved)

    def test_ignores_a_recorded_path_that_is_not_there(self):
        # The profile is written on the build PC, so its Windows paths do not
        # exist in a Linux container - falling through to PATH is correct.
        recorded = r"C:\Users\someone\AppData\codex.cmd"
        resolved = CodexRunner.resolve_binary(
            self.profile(status="OK", path=recorded))
        # Asserted as "not the recorded path", NOT as "contains no drive
        # letter": ON THE BUILD PC the correct fallback is itself a C:\ path,
        # so the old wording failed there and only there. A suite that is red
        # on the one machine that matters teaches people to ignore it.
        self.assertNotEqual(recorded, resolved)

    def test_ignores_a_recorded_path_when_the_probe_did_not_pass(self):
        shim = self.root / "codex.cmd"
        shim.write_text("@echo off", encoding="utf-8")
        resolved = CodexRunner.resolve_binary(
            self.profile(status="MISSING", path=str(shim)))
        self.assertNotEqual(str(shim), resolved)

    def test_missing_profile_is_not_an_error(self):
        self.assertTrue(CodexRunner.resolve_binary(self.root / "nope.json"))

    def test_unparsable_profile_is_not_an_error(self):
        path = self.root / "HARDWARE_PROFILE.json"
        path.write_text("{ not json", encoding="utf-8")
        self.assertTrue(CodexRunner.resolve_binary(path))

    def test_falls_back_to_a_name_rather_than_raising(self):
        # A binary that cannot be found has to arrive as a status through
        # is_available(), never as an exception out of resolution - the CLI
        # prints the resolved path before probing it.
        resolved = CodexRunner.resolve_binary(None)
        self.assertTrue(resolved)
        self.assertIn("codex", Path(resolved).name)

    def test_prefers_the_cmd_shim_over_the_extensionless_one(self):
        # The actual Windows failure: npm ships `codex`, `codex.cmd` and
        # `codex.ps1` side by side and only the .cmd can be launched, so the
        # extension has to be named explicitly rather than left to PATHEXT
        # (which subprocess does not apply). Asserted through PATH rather than
        # by reading the source, so it holds on either platform.
        bin_dir = self.root / "fakebin"
        bin_dir.mkdir()
        for name in ("codex", "codex.cmd"):
            target = bin_dir / name
            target.write_text("#!/bin/sh\n", encoding="utf-8")
            target.chmod(0o755)

        original = os.environ.get("PATH", "")
        os.environ["PATH"] = str(bin_dir) + os.pathsep + original
        try:
            resolved = CodexRunner.resolve_binary(None)
        finally:
            os.environ["PATH"] = original

        self.assertEqual(str(bin_dir / "codex.cmd"), resolved)

    def test_a_winerror_2_names_the_path_and_the_cause(self):
        # The exact failure seen on the PC. The message has to say WHICH path
        # was tried and why the bare name cannot work there.
        def explode(args, env, stdin_text=None):
            raise FileNotFoundError(2, "지정된 파일을 찾을 수 없습니다")

        runner = CodexRunner(repo_root=self.root, policy=policy_with(),
                             runner=explode, binary="codex")
        ok, detail = runner.is_available()
        self.assertFalse(ok)
        self.assertIn("tried: codex", detail)
        self.assertIn("PATHEXT", detail)
        self.assertIn("detect-environment.ps1", detail)


class WriteModeTests(RunnerTestCase):
    """implement() lets Codex edit the tree, so its gates matter most."""

    def _writable(self) -> Policy:
        return policy_with(allow_codex_write=True)

    def test_write_needs_its_own_policy_key(self):
        # The subscription being on must not by itself grant write access:
        # enabling the reviewer and enabling a co-developer are different
        # decisions with different blast radius.
        fake = FakeCodex()
        with self.assertRaises(PolicyViolation) as ctx:
            self.make(fake).implement("do the thing")
        self.assertIn("allow_codex_write", str(ctx.exception))
        self.assertEqual([], fake.calls, "nothing may be sent before the gate passes")

    def test_write_still_needs_the_subscription_gate(self):
        fake = FakeCodex()
        policy = policy_with(allow_codex_write=True, use_codex_subscription=False)
        with self.assertRaises(PolicyViolation):
            self.make(fake, policy).implement("do the thing")
        self.assertEqual([], fake.calls)

    def test_uses_workspace_write_not_full_access(self):
        fake = FakeCodex(writes="changed one file")
        self.make(fake, self._writable()).implement("do the thing")
        args = fake.calls[-1]
        self.assertIn("--sandbox", args)
        self.assertEqual("workspace-write", args[args.index("--sandbox") + 1])
        self.assertNotIn("danger-full-access", args)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)

    def test_review_is_unaffected_and_stays_read_only(self):
        # Turning write on must not widen the reviewer.
        fake = FakeCodex()
        self.make(fake, self._writable()).review("look at this")
        args = fake.calls[-1]
        self.assertEqual("read-only", args[args.index("--sandbox") + 1])

    def test_write_run_uses_only_probe_captured_flags(self):
        if not PROBE.is_file():
            self.skipTest("no codex probe committed")
        exec_section = PROBE.read_text(encoding="utf-8-sig").split(
            "### codex exec --help", 1)[-1]

        fake = FakeCodex(writes="done")
        self.make(fake, self._writable()).implement("do the thing")
        for flag in [a for a in fake.calls[-1] if a.startswith("--")]:
            self.assertIn(flag, exec_section,
                          f"{flag} is not in the captured codex exec --help")

    def test_silence_is_not_a_finished_task(self):
        fake = FakeCodex(writes=None)
        with self.assertRaises(ReviewNotRun) as ctx:
            self.make(fake, self._writable()).implement("do the thing")
        self.assertIn("(implement)", str(ctx.exception))

    def test_quota_exhaustion_degrades_here_too(self):
        # Exhausted means it delivered nothing, not merely that the word
        # appeared somewhere in the output.
        fake = FakeCodex(exit_code=1, stderr="429 rate limit exceeded", writes=None)
        with self.assertRaises(CodexLimited):
            self.make(fake, self._writable()).implement("do the thing")

    def test_an_implement_run_that_finished_survives_a_limit_warning(self):
        # The CODEX-OFFICE1 case, on the path that matters most: Codex edited
        # the tree, said the task was complete, and mentioned quota. Throwing
        # that away loses real work already written to disk.
        fake = FakeCodex(exit_code=0, stderr="warning: approaching usage limit",
                         writes="TASK complete. Changed files: dashboard.py")
        result = self.make(fake, self._writable()).implement("do the thing")

        self.assertTrue(result.ok)
        self.assertIn("dashboard.py", result.last_message)
        self.assertIn("usage limit", result.limit_warning)


class HonestResultTests(RunnerTestCase):
    def test_exit_zero_with_no_output_is_not_a_pass(self):
        # The section 38 case: silence must never become "no issues found".
        fake = FakeCodex(writes=None)
        with self.assertRaises(ReviewNotRun) as ctx:
            self.make(fake).review("hi")
        message = str(ctx.exception)
        self.assertIn("not a pass", message)
        # Names which kind of run went silent - review and implement share
        # this code path, and "an empty result" means different things to a
        # reader depending on which one produced it.
        self.assertIn("(review)", message)

    def test_empty_output_file_is_not_a_pass(self):
        fake = FakeCodex(writes="   \n  ")
        with self.assertRaises(ReviewNotRun):
            self.make(fake).review("hi")

    def test_failure_carries_the_raw_output(self):
        fake = FakeCodex(exit_code=2, stderr="panic: something broke")
        with self.assertRaises(ReviewNotRun) as ctx:
            self.make(fake).review("hi")
        self.assertIn("panic: something broke", str(ctx.exception))

    def test_auth_failure_names_the_human_gate(self):
        fake = FakeCodex(exit_code=1, stderr="Error: not logged in")
        with self.assertRaises(ReviewNotRun) as ctx:
            self.make(fake).review("hi")
        self.assertIn("HUMAN_GATE", str(ctx.exception))

    def test_a_real_review_comes_back(self):
        fake = FakeCodex(writes="Found 2 issues in PlayerController.cs")
        result = self.make(fake).review("hi")
        self.assertTrue(result.ok)
        self.assertIn("PlayerController", result.last_message)
        self.assertTrue(result.output_path.is_file())

    def test_missing_binary_is_unavailable_not_a_pass(self):
        def explode(args, env, stdin_text=None):
            raise OSError("No such file or directory: 'codex'")
        with self.assertRaises(CodexUnavailable):
            self.make(explode).review("hi")

    def test_is_available_reports_rather_than_raises(self):
        def explode(args, env, stdin_text=None):
            raise OSError("missing")
        ok, detail = self.make(explode).is_available()
        self.assertFalse(ok)
        self.assertIn("missing", detail)


class JsonReviewTests(RunnerTestCase):
    def test_parses_a_schema_conforming_answer(self):
        fake = FakeCodex(writes='{"findings": ["a", "b"]}')
        data = self.make(fake).review_json("hi", SCHEMA)
        self.assertEqual(data["findings"], ["a", "b"])

    def test_unwraps_a_fenced_code_block(self):
        fake = FakeCodex(writes='```json\n{"findings": []}\n```')
        self.assertEqual(self.make(fake).review_json("hi", SCHEMA), {"findings": []})

    def test_unparseable_output_is_not_treated_as_zero_findings(self):
        fake = FakeCodex(writes="I could not complete the review.")
        with self.assertRaises(ReviewNotJson) as ctx:
            self.make(fake).review_json("hi", SCHEMA)
        self.assertIn("Not treating", str(ctx.exception))


class StatusTests(RunnerTestCase):
    def test_summary_defers_login_to_a_human_instead_of_guessing(self):
        summary = self.make(FakeCodex()).status_summary()
        self.assertIn("HUMAN_GATE", summary)
        self.assertIn("secrets_never_touched", summary)
        # It must not claim a login state it has no way to know.
        self.assertNotIn("logged in", summary)

    def test_summary_names_stripped_keys_without_printing_values(self):
        import os
        os.environ["OPENAI_API_KEY"] = "sk-should-never-appear"
        try:
            summary = self.make(FakeCodex()).status_summary()
        finally:
            del os.environ["OPENAI_API_KEY"]
        self.assertIn("OPENAI_API_KEY", summary)
        self.assertNotIn("sk-should-never-appear", summary)

    def test_doctor_output_is_returned_raw_not_interpreted(self):
        fake = FakeCodex(stdout="auth: ok\nconfig: ok")
        result = self.make(fake).doctor()
        self.assertIn("auth: ok", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
