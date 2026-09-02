"""Tests for the AI status dashboard.

Run:  python3 AI_GAME_COMPANY/tests/test_dashboard.py

The rule these exist to protect is the one the page is built around: absence
of evidence renders as "확인 불가", never as OK. A dashboard that upgrades
"not checked" to "fine" is worse than no dashboard, so most of what follows
is about what happens when a file is missing, empty or says UNKNOWN.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.orchestrator import dashboard as dash  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

BUILD_REPORT = """\
# Build status report

Generated: 2026-08-27 21:36:25
Findings-Hash: 4DFA10A6F3F05F57

## game01

- [CiWorkspacePath] Builds\\game01\\APK\\Game01_FactoryRunner_v1.0.apk  (17.24 MB, sha256:6F0E78431668FD15, built 2026-08-27 21:15:14)
"""

ERROR_REPORT = """\
# Unity error report

Generated: 2026-08-29 22:00:28

## Compile errors (3)
## Obsolete API warnings (CS0618) (0)
## Runtime exceptions (1)
"""


def profile(**overrides):
    base = {
        "machineName": "TEST-PC",
        "hardware": {"ramTotalGb": 15.71},
        "tools": {
            "claude": {"installed": True, "version": "2.1.247"},
            "codex": {"installed": True, "version": "codex-cli 0.151.0"},
            "ollama": {"installed": True, "version": "0.33.2"},
            "blender": {"installed": True, "version": "Blender 5.2.1 LTS"},
        },
        "ollamaApi": {"reachable": True, "models": []},
        "paidApiKeysPresent": {},
        "unity": {"requiredByProject": "6000.5.9f1", "status": "OK"},
    }
    base.update(overrides)
    return base


def policy(**overrides):
    base = {
        "use_claude_code": True,
        "use_codex_subscription": True,
        "allow_codex_write": True,
        "allow_local_image_generation": True,
        "human_gates": ["initial_codex_login"],
    }
    base.update(overrides)
    return base


def find(agents, prefix):
    for agent in agents:
        if agent.name.startswith(prefix):
            return agent
    raise AssertionError(f"no agent named {prefix!r} in {[a.name for a in agents]}")


class ReportParsingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_the_real_build_line(self):
        path = self.dir / "build.txt"
        path.write_text(BUILD_REPORT, encoding="utf-8")
        builds, when = dash.read_builds(path)

        self.assertEqual(1, len(builds))
        self.assertEqual("game01", builds[0]["game"])
        self.assertEqual("17.24 MB", builds[0]["size"])
        self.assertEqual("6F0E78431668FD15", builds[0]["sha"])
        self.assertEqual("2026-08-27 21:36:25", when)

    def test_a_missing_build_report_is_no_builds_not_a_crash(self):
        builds, when = dash.read_builds(self.dir / "nope.txt")
        self.assertEqual([], builds)
        self.assertEqual("", when)

    def test_reads_error_counts_including_zero(self):
        path = self.dir / "errors.txt"
        path.write_text(ERROR_REPORT, encoding="utf-8")
        counts, when = dash.read_errors(path)

        self.assertEqual({"compile": 3, "obsolete": 0, "runtime": 1}, counts)
        self.assertEqual("2026-08-29 22:00:28", when)

    def test_a_missing_error_report_yields_no_counts(self):
        # Not zeros: zero compile errors is a finding, and a missing report is
        # not that finding.
        counts, _ = dash.read_errors(self.dir / "nope.txt")
        self.assertEqual({}, counts)


class AgentStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.company = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def agents(self, prof=None, pol=None, licences=None):
        return dash.build_agents(
            profile() if prof is None else prof,
            policy() if pol is None else pol,
            licences or {}, self.company)

    def test_no_hardware_report_means_unknown_not_ready(self):
        agents = self.agents(prof={})
        self.assertEqual(dash.UNKNOWN, find(agents, "Claude Code").state)
        self.assertEqual([], find(agents, "Claude Code").evidence,
                         "a row with no evidence must not cite any")

    def test_claude_is_ready_when_installed_and_allowed(self):
        agents = self.agents()
        claude = find(agents, "Claude Code")
        self.assertEqual(dash.READY, claude.state)
        self.assertIn("config/HARDWARE_PROFILE.json", claude.evidence)

    def test_codex_is_gated_on_login_even_when_everything_else_passes(self):
        # Login cannot be inferred here: ~/.codex/auth.json is on the policy's
        # secrets_never_touched list and initial_codex_login is a HUMAN_GATE.
        # "Installed and allowed" is therefore never "ready".
        codex = find(self.agents(), "Codex CLI")
        self.assertEqual(dash.GATED, codex.state)
        self.assertIn("doctor", codex.detail)

    def test_codex_without_write_policy_says_review_only(self):
        codex = find(self.agents(pol=policy(allow_codex_write=False)), "Codex CLI")
        self.assertIn("리뷰", codex.role)
        self.assertIn("allow_codex_write", codex.detail)

    def test_a_model_that_fails_licence_and_ram_reports_both(self):
        # Naming only the first failure hides the second, and someone would
        # then get the licence approved and still be unable to load it.
        prof = profile(ollamaApi={"reachable": True, "models": [
            {"name": "gemma4:26b", "sizeGb": 17.33,
             "parameterSize": "25.2B", "quantization": "Q4_K_M"}]})
        agent = find(self.agents(prof=prof), "Ollama · gemma4")
        self.assertEqual(dash.BLOCKED, agent.state)
        self.assertIn("라이선스 UNKNOWN", agent.detail)
        self.assertIn("적재 불가", agent.detail)

    def test_an_approved_model_that_fits_is_ready(self):
        prof = profile(ollamaApi={"reachable": True, "models": [
            {"name": "llama3.2:3b", "sizeGb": 2.0,
             "parameterSize": "3.2B", "quantization": "Q4_K_M"}]})
        agent = find(self.agents(prof=prof, licences={"llama3.2:3b": "APPROVED"}),
                     "Ollama · llama3.2")
        self.assertEqual(dash.READY, agent.state)

    def test_no_installed_model_is_gated_not_ready(self):
        agent = find(self.agents(), "Ollama (로컬 LLM)")
        self.assertEqual(dash.GATED, agent.state)

    def test_image_generation_is_gated_until_something_was_produced(self):
        agent = find(self.agents(licences={"stable-diffusion-v1-5": "APPROVED"}),
                     "Stable Diffusion")
        self.assertEqual(dash.GATED, agent.state)

        # An approved licence and a permissive policy are not output. A PNG is.
        (self.company / "generated" / "dori").mkdir(parents=True)
        (self.company / "generated" / "dori" / "a.png").write_bytes(b"x")
        agent = find(self.agents(licences={"stable-diffusion-v1-5": "APPROVED"}),
                     "Stable Diffusion")
        self.assertEqual(dash.READY, agent.state)

    def test_image_generation_blocked_by_policy_beats_everything(self):
        (self.company / "generated").mkdir(parents=True)
        (self.company / "generated" / "a.png").write_bytes(b"x")
        agent = find(self.agents(pol=policy(allow_local_image_generation=False)),
                     "Stable Diffusion")
        self.assertEqual(dash.BLOCKED, agent.state)

    def test_an_approved_but_unusable_model_is_blocked(self):
        agent = find(self.agents(licences={"qwen-image": "APPROVED_BUT_UNUSABLE_HERE"}),
                     "Qwen-Image")
        self.assertEqual(dash.BLOCKED, agent.state)
        self.assertIn("15.7", agent.detail)

    def test_blender_installed_without_an_adapter_is_unknown(self):
        agent = find(self.agents(), "Blender")
        self.assertEqual(dash.UNKNOWN, agent.state)
        self.assertIn("blender_runner.py", agent.detail)

    def test_blender_with_an_adapter_is_ready(self):
        (self.company / "company" / "orchestrator").mkdir(parents=True)
        (self.company / "company" / "orchestrator" / "blender_runner.py").write_text("x")
        self.assertEqual(dash.READY, find(self.agents(), "Blender").state)

    def test_paid_apis_are_always_blocked_and_keys_are_named_not_printed(self):
        prof = profile(paidApiKeysPresent={"OPENAI_API_KEY": True,
                                           "GOOGLE_API_KEY": False})
        agent = find(self.agents(prof=prof), "유료 API")
        self.assertEqual(dash.BLOCKED, agent.state)
        self.assertIn("OPENAI_API_KEY", agent.detail)
        self.assertNotIn("GOOGLE_API_KEY", agent.detail)


class GameProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        (self.repo / "GameSpecs").mkdir()
        (self.repo / "Reports").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_ten_cells_regardless_of_what_exists(self):
        self.assertEqual(10, len(dash.read_games(self.repo, [])))

    def test_a_spec_alone_is_active_not_done(self):
        (self.repo / "GameSpecs" / "game01.json").write_text("{}")
        games = dash.read_games(self.repo, [])
        self.assertEqual("active", games[0]["state"])

    def test_a_report_without_an_apk_is_not_done(self):
        # Section 38: the report is a claim. The APK is the fact.
        (self.repo / "GameSpecs" / "game01.json").write_text("{}")
        (self.repo / "Reports" / "Game01_Report.txt").write_text("done!")
        self.assertEqual("active", dash.read_games(self.repo, [])[0]["state"])

    def test_a_report_and_a_real_apk_is_done(self):
        (self.repo / "GameSpecs" / "game01.json").write_text("{}")
        (self.repo / "Reports" / "Game01_Report.txt").write_text("done!")
        games = dash.read_games(self.repo, [{"game": "game01"}])
        self.assertEqual("done", games[0]["state"])
        self.assertEqual("todo", games[1]["state"])


class RenderTests(unittest.TestCase):
    def test_shortens_a_path_to_its_filename(self):
        self.assertEqual("SceneGenerator.cs",
                         dash._short_path("Assets/GameFactory/Editor/SceneGenerator.cs"))
        self.assertEqual("UI/", dash._short_path("Assets/GameFactory/UI/"))
        self.assertEqual("SharedArtImporter.cs",
                         dash._short_path("Assets\\GameFactory\\Editor\\SharedArtImporter.cs"))

    def test_task_titles_are_escaped(self):
        # Board content is hand-edited JSON and Codex can be asked to touch
        # it; it reaches the page as text, never as markup.
        row = dash._task_row({"id": "X", "title": "<script>alert(1)</script>",
                              "status": "todo", "files": []})
        self.assertNotIn("<script>", row)
        self.assertIn("&lt;script&gt;", row)

    def test_renders_the_real_repository(self):
        snapshot = dash.collect(REPO)
        page = dash.render(snapshot)

        self.assertIn("<title>", page)
        self.assertIn("Claude Code", page)
        self.assertIn("Codex CLI", page)
        # Every state token used by the roster needs its CSS class defined,
        # or a row renders with no severity colour at all.
        for agent in snapshot.agents:
            self.assertIn(f".s-{agent.state}{{", dash.CSS.replace(" ", ""))

    def test_every_theme_token_is_defined_in_bare_root(self):
        # The classic unreadable-artifact bug: a colour whose only definition
        # sits inside a media query never applies in the un-stamped state.
        bare = dash.CSS.split("@media", 1)[0]
        used = set(dash.__dict__ and __import__("re").findall(r"var\((--[\w-]+)\)", dash.CSS))
        for token in used:
            self.assertIn(f"{token}:", bare, f"{token} is never defined on bare :root")

    def test_missing_files_are_listed_not_silently_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = dash.collect(Path(tmp))
            self.assertIn("config/HARDWARE_PROFILE.json", snapshot.missing)
            self.assertIn("근거 없음", dash.render(snapshot))

    def test_write_produces_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "sub" / "dashboard.html"
            self.assertEqual(out, dash.write(REPO, out))
            self.assertGreater(out.stat().st_size, 4000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
