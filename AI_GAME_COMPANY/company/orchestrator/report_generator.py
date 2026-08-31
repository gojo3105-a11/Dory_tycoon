"""Writes Reports/GameXX_Report.txt. Master prompt sections 33 and 34.

DESIGN NOTE - the report cannot be told to lie.

Section 33 lists the sections a game report must contain, and section 38
forbids reporting a build as complete without an APK. The obvious way to
write this module would be to accept a dict of strings and format it - which
would let a caller (human or agent) state "APK: built successfully" for a
build that never produced a file.

So the fields split in two:

  DERIVED  - read from disk and never accepted as input: whether an APK
             exists, its size, sha256 and timestamp, its version (parsed out
             of the filename the build actually wrote), the licence status of
             every asset, and the compile-error count. If the APK is absent
             the report says so, and no argument can change that.

  NARRATIVE - genuinely human/agent-authored: how the game plays, what makes
             it different, the controls. These are the parts no filesystem
             check can supply, and section 33 marks three of them as the
             minimum required, so a missing one is an error rather than a
             blank line.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

BUNDLE_ID_PREFIX = "com.gamefactory."

# Game01_FactoryRunner_v1.0.apk -> version "1.0"
APK_VERSION_RE = re.compile(r"_v(?P<version>[0-9][0-9A-Za-z._-]*)\.(apk|aab)$", re.I)


class MissingRequiredSection(ValueError):
    """Section 33's minimum: genre, how to play, what makes it different."""


class WouldDowngradeReport(RuntimeError):
    """Refusing to replace a report that recorded an APK with one that cannot see it.

    This is not hypothetical: running the generator in an environment without
    the build output (the Linux container, or the PC after Builds/ is cleaned)
    produces a report saying "no APK" that is true THERE and false where the
    build actually happened - and overwrites the good one. The regression is
    silent, which is the worst kind.
    """


@dataclass
class GameNarrative:
    """The parts a filesystem check cannot supply."""

    how_to_play: str = ""
    what_makes_it_different: str = ""
    controls: str = ""
    goal: str = ""
    progression: str = ""
    map_description: str = ""
    character_notes: str = ""
    character_route: str = ""  # "A" (image-to-3D) or "B" (pre-rigged + appearance)
    known_issues: list[str] = field(default_factory=list)
    next_version: list[str] = field(default_factory=list)
    ai_usage: dict[str, str] = field(default_factory=dict)


@dataclass
class ApkFacts:
    exists: bool
    path: Path | None = None
    size_bytes: int = 0
    sha256_short: str = ""
    built_at: str = ""
    version: str = ""

    @property
    def size_mb(self) -> str:
        return f"{self.size_bytes / (1024 * 1024):.2f} MB" if self.size_bytes else "0"


class ReportGenerator:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    # ---- derived facts ---------------------------------------------------

    def load_spec(self, game_id: str) -> dict:
        path = self.repo_root / "GameSpecs" / f"{game_id}.json"
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def apk_facts(self, game_id: str) -> ApkFacts:
        build_dir = self.repo_root / "Builds" / game_id
        if not build_dir.is_dir():
            return ApkFacts(exists=False)

        found = [
            p for pattern in ("**/*.apk", "**/*.aab")
            for p in build_dir.glob(pattern)
            if p.is_file() and p.stat().st_size > 0
        ]
        if not found:
            return ApkFacts(exists=False)

        newest = max(found, key=lambda p: p.stat().st_mtime)
        stat = newest.stat()
        digest = hashlib.sha256(newest.read_bytes()).hexdigest().upper()[:16]
        match = APK_VERSION_RE.search(newest.name)

        return ApkFacts(
            exists=True,
            path=newest,
            size_bytes=stat.st_size,
            sha256_short=digest,
            built_at=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
            # Parsed from the name the build actually wrote, not from a
            # ProjectSettings value this repo does not even track.
            version=match.group("version") if match else "UNKNOWN",
        )

    def asset_licenses(self, game_id: str) -> tuple[list[str], list[str]]:
        """(approved lines, problem lines) for assets used by this game."""
        registry_path = (
            self.repo_root / "AI_GAME_COMPANY" / "config" / "LICENSE_REGISTRY.json"
        )
        if not registry_path.is_file():
            return [], ["LICENSE_REGISTRY.json not found - licence status UNVERIFIABLE"]

        registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
        approved: list[str] = []
        problems: list[str] = []

        for entry in registry.get("entries", []):
            games = entry.get("games") or []
            if game_id not in games:
                continue
            line = f"{entry.get('name')} - {entry.get('license')} [{entry.get('status')}]"
            if entry.get("status") == "APPROVED":
                approved.append(line)
            else:
                # Section 38: an UNKNOWN-licence asset must not ship, so it is
                # surfaced as a problem in the report rather than listed
                # alongside the cleared ones.
                problems.append(line)

        return approved, problems

    def compile_error_count(self) -> tuple[int | None, str]:
        """From the committed error report, or None when it is absent."""
        path = self.repo_root / "Reports" / "errors" / "latest.txt"
        if not path.is_file():
            return None, "Reports/errors/latest.txt not present"

        text = path.read_text(encoding="utf-8-sig", errors="replace")
        match = re.search(r"##\s*Compile errors\s*\((\d+)\)", text)
        generated = re.search(r"Generated:\s*(.+)", text)
        stamp = generated.group(1).strip() if generated else "unknown time"
        if not match:
            return None, f"could not parse the error report ({stamp})"
        return int(match.group(1)), stamp

    # ---- rendering -------------------------------------------------------

    def render(self, game_id: str, narrative: GameNarrative) -> str:
        spec = self.load_spec(game_id)
        game = spec.get("game", {})
        title = game.get("title") or game_id
        genre = game.get("genre") or ""

        # Section 33's stated minimum. Refusing here beats emitting a report
        # with three empty headings that reads as if it were complete.
        missing = [
            name for name, value in (
                ("게임 종류(genre)", genre),
                ("게임 방법(how_to_play)", narrative.how_to_play),
                ("게임 특징(what_makes_it_different)", narrative.what_makes_it_different),
            ) if not str(value).strip()
        ]
        if missing:
            raise MissingRequiredSection(
                "section 33 requires these and they are empty: " + ", ".join(missing)
            )

        apk = self.apk_facts(game_id)
        approved, problems = self.asset_licenses(game_id)
        errors, error_stamp = self.compile_error_count()

        number = game_id.replace("game", "").lstrip("0") or game_id
        lines: list[str] = []
        add = lines.append

        add("=" * 70)
        add(f"게임 번호 : {number}")
        add(f"게임 이름 : {title}")
        add(f"게임 종류 : {genre}")
        add("=" * 70)
        add(f"작성 : {time.strftime('%Y-%m-%d %H:%M:%S')}")
        add("작성 도구 : AI_GAME_COMPANY report_generator.py")
        add("")
        add("이 보고서의 [APK] / [Asset] / [QA] 항목은 서술이 아니라 디스크와")
        add("LICENSE_REGISTRY.json에서 읽은 값이다. APK가 없으면 없다고 적힌다.")
        add("")

        add("[게임 방법]")
        add(narrative.how_to_play.strip())
        add("")

        add("[게임 특징]")
        add(narrative.what_makes_it_different.strip())
        add("")

        for heading, value in (
            ("조작 방법", narrative.controls),
            ("게임 목표", narrative.goal),
            ("성장 요소", narrative.progression),
            ("맵", narrative.map_description),
        ):
            add(f"[{heading}]")
            add(value.strip() if value.strip() else "(미작성)")
            add("")

        add("[캐릭터]")
        theme_character = (spec.get("theme") or {}).get("character") or "(GameSpec에 없음)"
        add(f"  GameSpec theme.character : {theme_character}")
        add(f"  공통 캐릭터 사용         : 예 (Assets/Common/Character/)")
        route = narrative.character_route.strip().upper()
        if route in ("A", "B"):
            route_label = {
                "A": "Route A (이미지 -> 3D 재구성)",
                "B": "Route B (라이선스 pre-rigged 휴머노이드 + 외형 재현)",
            }[route]
            add(f"  Character Route          : {route_label}")
        else:
            add("  Character Route          : 미정 (A/B 어느 쪽도 확정되지 않음)")
        if narrative.character_notes.strip():
            add(f"  비고                     : {narrative.character_notes.strip()}")
        add("")

        add("[사용 AI]")
        if narrative.ai_usage:
            for tool, what in narrative.ai_usage.items():
                add(f"  {tool:12} {what}")
        else:
            add("  (기록 없음)")
        add("")

        add("[Asset]")
        if approved:
            for line in approved:
                add(f"  APPROVED : {line}")
        else:
            add("  이 게임에 등록된 APPROVED 에셋이 없다")
        if problems:
            add("")
            for line in problems:
                add(f"  !! 문제  : {line}")
            add("  -> 마스터 프롬프트 §38: 라이선스 UNKNOWN 에셋은 출시 APK에 넣지 않는다")
        add("")

        add("[QA]")
        if errors is None:
            add(f"  Compile        : 확인 불가 ({error_stamp})")
        elif errors == 0:
            add(f"  Compile        : 에러 0개 (리포트 생성 {error_stamp})")
        else:
            add(f"  Compile        : !! 에러 {errors}개 (리포트 생성 {error_stamp})")
        add(f"  Android Build  : {'APK 생성 확인' if apk.exists else '!! APK 없음'}")
        add("  Gameplay       : 사람 플레이테스트 필요 - AI가 재미를 판정하지 않는다 (§30)")
        add("")

        add("[APK]")
        if apk.exists and apk.path is not None:
            add(f"  파일명       : {apk.path.name}")
            add(f"  경로         : {apk.path.relative_to(self.repo_root)}")
            add(f"  Package Name : {BUNDLE_ID_PREFIX}{game_id}")
            add(f"  Version      : {apk.version}  (파일명에서 파싱)")
            add(f"  크기         : {apk.size_mb}")
            add(f"  sha256       : {apk.sha256_short}")
            add(f"  빌드 시각    : {apk.built_at}")
            add("  파일 존재    : 예 (이 보고서 생성 시점에 실측)")
        else:
            add("  파일 존재    : !! 아니오")
            add(f"  Builds/{game_id}/ 아래에 크기가 0보다 큰 .apk/.aab가 없다.")
            add("  §38에 따라 이 게임은 빌드 성공으로 보고할 수 없다.")
        add("")

        add("[알려진 문제]")
        issues = list(narrative.known_issues)
        # Facts that must appear whether or not the author remembered them.
        if not apk.exists:
            issues.insert(0, "APK가 생성되지 않았다 (위 [APK] 항목 참고)")
        if errors:
            issues.insert(0, f"컴파일 에러 {errors}개가 남아 있다")
        if problems:
            issues.insert(0, "라이선스가 APPROVED가 아닌 에셋이 등록되어 있다")
        if issues:
            for issue in issues:
                add(f"  - {issue}")
        else:
            add("  (없음)")
        add("")

        add("[다음 버전 개선사항]")
        if narrative.next_version:
            for item in narrative.next_version:
                add(f"  - {item}")
        else:
            add("  (미작성)")
        add("")

        return "\n".join(lines) + "\n"

    def report_path(self, game_id: str) -> Path:
        number = game_id.replace("game", "").zfill(2) if game_id.startswith("game") else game_id
        return self.repo_root / "Reports" / f"Game{number}_Report.txt"

    def write(self, game_id: str, narrative: GameNarrative, force: bool = False) -> Path:
        content = self.render(game_id, narrative)
        path = self.report_path(game_id)

        if not force and path.is_file():
            existing = path.read_text(encoding="utf-8-sig", errors="replace")
            existing_had_apk = ".apk" in existing.lower() or ".aab" in existing.lower()
            if existing_had_apk and not self.apk_facts(game_id).exists:
                raise WouldDowngradeReport(
                    f"{path.name} already records an APK, but no APK is visible from "
                    f"{self.repo_root}. Writing here would replace a true report with "
                    "one that is only true on this machine. Run this where the build "
                    "output lives, or pass force=True if the APK is genuinely gone."
                )

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def is_complete(self, game_id: str) -> tuple[bool, list[str]]:
        """Whether this game may be called COMPLETE.

        Section 23 forbids starting the next game until this one is complete,
        and section 38 forbids calling it complete without an APK - so this is
        a filesystem check, not a judgement call.
        """
        blockers: list[str] = []

        apk = self.apk_facts(game_id)
        if not apk.exists:
            blockers.append("no APK on disk")

        errors, _ = self.compile_error_count()
        if errors is None:
            blockers.append("compile error count unverifiable")
        elif errors > 0:
            blockers.append(f"{errors} compile error(s)")

        _, problems = self.asset_licenses(game_id)
        if problems:
            blockers.append(f"{len(problems)} asset(s) not APPROVED")

        number = game_id.replace("game", "").zfill(2) if game_id.startswith("game") else game_id
        if not (self.repo_root / "Reports" / f"Game{number}_Report.txt").is_file():
            blockers.append("report file missing")

        return (not blockers), blockers
