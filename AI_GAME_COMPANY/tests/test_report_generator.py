"""Tests for the game report generator.

Run:  python3 AI_GAME_COMPANY/tests/test_report_generator.py

The point of these is the anti-lying property. Section 38 forbids reporting a
build as successful with no APK, and section 33 sets a minimum set of
sections. So the tests mostly try to MAKE the generator produce a false
report, and assert that it refuses or contradicts the caller.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.orchestrator.report_generator import (  # noqa: E402
    GameNarrative, MissingRequiredSection, ReportGenerator, WouldDowngradeReport,
)


def full_narrative(**overrides) -> GameNarrative:
    base = dict(
        how_to_play="화면을 탭하면 점프한다. 장애물을 피하고 코인을 모은다.",
        what_makes_it_different="중력 전환 구간에서 위아래가 뒤집힌다.",
        controls="한 손 탭",
        goal="최대한 멀리 달린다",
        progression="코인으로 상점 아이템 구매",
        map_description="절차 생성 무한 지형",
        character_route="B",
    )
    base.update(overrides)
    return GameNarrative(**base)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "GameSpecs").mkdir(parents=True)
        (self.root / "GameSpecs" / "game01.json").write_text(json.dumps({
            "game": {"id": "game01", "title": "Factory Runner", "genre": "Runner"},
            "theme": {"environment": "Factory", "character": "Dori_Default"},
        }), encoding="utf-8")
        self.gen = ReportGenerator(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    # ---- helpers ----

    def _write_apk(self, name="Game01_FactoryRunner_v1.0.apk", size=2048):
        d = self.root / "Builds" / "game01" / "APK"
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        p.write_bytes(b"z" * size)
        return p

    def _write_error_report(self, count=0):
        d = self.root / "Reports" / "errors"
        d.mkdir(parents=True, exist_ok=True)
        (d / "latest.txt").write_text(
            f"Generated: 2026-08-31 20:55:48\n\n## Compile errors ({count})\n\nNone.\n",
            encoding="utf-8",
        )

    def _write_registry(self, status="APPROVED"):
        d = self.root / "AI_GAME_COMPANY" / "config"
        d.mkdir(parents=True, exist_ok=True)
        (d / "LICENSE_REGISTRY.json").write_text(json.dumps({
            "entries": [{
                "id": "pack", "name": "Test Pack", "license": "CC0 1.0",
                "status": status, "games": ["game01"],
            }]
        }), encoding="utf-8")

    # ---- section 33 minimum ----

    def test_missing_how_to_play_is_refused(self):
        with self.assertRaises(MissingRequiredSection) as ctx:
            self.gen.render("game01", full_narrative(how_to_play=""))
        self.assertIn("게임 방법", str(ctx.exception))

    def test_missing_differentiator_is_refused(self):
        with self.assertRaises(MissingRequiredSection):
            self.gen.render("game01", full_narrative(what_makes_it_different=""))

    def test_missing_genre_in_spec_is_refused(self):
        (self.root / "GameSpecs" / "game02.json").write_text(json.dumps({
            "game": {"id": "game02", "title": "No Genre"}
        }), encoding="utf-8")
        with self.assertRaises(MissingRequiredSection) as ctx:
            self.gen.render("game02", full_narrative())
        self.assertIn("게임 종류", str(ctx.exception))

    def test_whitespace_only_does_not_satisfy_a_required_section(self):
        with self.assertRaises(MissingRequiredSection):
            self.gen.render("game01", full_narrative(how_to_play="   \n  "))

    # ---- section 38: cannot claim a build that did not happen ----

    def test_no_apk_is_stated_plainly(self):
        self._write_error_report(0)
        text = self.gen.render("game01", full_narrative())
        self.assertIn("파일 존재    : !! 아니오", text)
        self.assertIn("빌드 성공으로 보고할 수 없다", text)
        self.assertIn("Android Build  : !! APK 없음", text)

    def test_missing_apk_is_forced_into_known_issues(self):
        # Even when the author lists no issues at all.
        self._write_error_report(0)
        text = self.gen.render("game01", full_narrative(known_issues=[]))
        self.assertIn("APK가 생성되지 않았다", text)

    def test_zero_byte_apk_does_not_count_as_built(self):
        self._write_apk(size=0)
        self._write_error_report(0)
        text = self.gen.render("game01", full_narrative())
        self.assertIn("!! 아니오", text)

    def test_real_apk_is_measured_not_described(self):
        apk = self._write_apk(size=4096)
        self._write_error_report(0)
        text = self.gen.render("game01", full_narrative())
        self.assertIn(apk.name, text)
        self.assertIn("0.00 MB", text)          # 4096 bytes, honestly rounded
        self.assertIn("Version      : 1.0", text)  # parsed from the filename
        self.assertIn("com.gamefactory.game01", text)
        self.assertIn("파일 존재    : 예", text)

    def test_version_unknown_when_filename_has_none(self):
        self._write_apk(name="Game01.apk")
        self._write_error_report(0)
        self.assertIn("Version      : UNKNOWN", self.gen.render("game01", full_narrative()))

    # ---- compile errors and licences are read, not asserted ----

    def test_compile_errors_are_surfaced(self):
        self._write_apk()
        self._write_error_report(count=5)
        text = self.gen.render("game01", full_narrative())
        self.assertIn("!! 에러 5개", text)
        self.assertIn("컴파일 에러 5개가 남아 있다", text)

    def test_unverifiable_compile_state_says_so(self):
        self._write_apk()
        text = self.gen.render("game01", full_narrative())
        self.assertIn("확인 불가", text)

    def test_unapproved_licence_is_flagged_not_listed_as_fine(self):
        self._write_apk()
        self._write_error_report(0)
        self._write_registry(status="UNKNOWN")
        text = self.gen.render("game01", full_narrative())
        self.assertIn("!! 문제", text)
        self.assertIn("38", text)  # cites the rule it would violate

    def test_approved_licence_is_listed(self):
        self._write_apk()
        self._write_error_report(0)
        self._write_registry(status="APPROVED")
        self.assertIn("APPROVED : Test Pack", self.gen.render("game01", full_narrative()))

    # ---- completeness gate (section 23 / 38) ----

    def test_not_complete_without_apk(self):
        self._write_error_report(0)
        ok, blockers = self.gen.is_complete("game01")
        self.assertFalse(ok)
        self.assertIn("no APK on disk", blockers)

    def test_not_complete_with_compile_errors(self):
        self._write_apk()
        self._write_error_report(count=3)
        ok, blockers = self.gen.is_complete("game01")
        self.assertFalse(ok)
        self.assertIn("3 compile error(s)", blockers)

    def test_complete_when_everything_checks_out(self):
        self._write_apk()
        self._write_error_report(0)
        self._write_registry("APPROVED")
        self.gen.write("game01", full_narrative())
        ok, blockers = self.gen.is_complete("game01")
        self.assertTrue(ok, f"unexpected blockers: {blockers}")

    def test_report_is_not_complete_until_written(self):
        self._write_apk()
        self._write_error_report(0)
        self._write_registry("APPROVED")
        ok, blockers = self.gen.is_complete("game01")
        self.assertFalse(ok)
        self.assertIn("report file missing", blockers)

    # ---- output ----

    def test_write_uses_the_expected_filename(self):
        self._write_error_report(0)
        path = self.gen.write("game01", full_narrative())
        self.assertEqual(path.name, "Game01_Report.txt")
        self.assertTrue(path.read_text(encoding="utf-8").startswith("="))

    def test_character_route_is_named_not_assumed(self):
        self._write_error_report(0)
        text = self.gen.render("game01", full_narrative(character_route=""))
        self.assertIn("미정", text)
        text_b = self.gen.render("game01", full_narrative(character_route="B"))
        self.assertIn("Route B", text_b)

    # ---- must not clobber a truthful report from another machine ----

    def test_refuses_to_replace_an_apk_report_when_no_apk_is_visible(self):
        """The accident this guard exists for, reproduced.

        Running the generator where the build output does not live produced a
        "no APK" report and overwrote the real one. True here, false there.
        """
        self._write_error_report(0)
        existing = self.gen.report_path("game01")
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text(
            "파일명 : Game01_FactoryRunner_v1.0.apk\n크기 : 17.24 MB\n", encoding="utf-8"
        )
        before = existing.read_text(encoding="utf-8")

        with self.assertRaises(WouldDowngradeReport):
            self.gen.write("game01", full_narrative())

        self.assertEqual(existing.read_text(encoding="utf-8"), before)

    def test_force_allows_the_overwrite(self):
        self._write_error_report(0)
        existing = self.gen.report_path("game01")
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text("Game01_FactoryRunner_v1.0.apk\n", encoding="utf-8")

        self.gen.write("game01", full_narrative(), force=True)
        self.assertIn("!! 아니오", existing.read_text(encoding="utf-8"))

    def test_overwrite_is_fine_when_the_apk_is_actually_there(self):
        self._write_apk()
        self._write_error_report(0)
        existing = self.gen.report_path("game01")
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text("Game01_FactoryRunner_v1.0.apk\n", encoding="utf-8")

        self.gen.write("game01", full_narrative())
        self.assertIn("파일 존재    : 예", existing.read_text(encoding="utf-8"))

    def test_no_existing_report_writes_freely(self):
        self._write_error_report(0)
        path = self.gen.write("game01", full_narrative())
        self.assertTrue(path.is_file())

    def test_gameplay_qa_always_defers_to_a_human(self):
        # Section 30: the AI does not get to declare the game fun.
        self._write_apk()
        self._write_error_report(0)
        self.assertIn("사람 플레이테스트 필요", self.gen.render("game01", full_narrative()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
