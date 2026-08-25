# Game Factory

Unity + Claude Code + GitHub Actions를 연결해서, 사람의 개입을 최소화하며 Android 모바일 게임을
GameSpec 파일 하나로 자동 생성/검증/테스트/빌드하는 시스템입니다.

```text
GameSpec(JSON) → Unity Editor 자동 생성기 → Scene/Prefab/Level/UI 생성
→ Validation → Unity Test → Android Build → APK/AAB
```

게임마다 코드를 새로 짜지 않습니다. 재사용 가능한 `Core`/`Modules`/`Gameplay` 코드와 `GameSpecs/*.json`
설정을 조합해서 게임을 "생성"합니다. 지금은 Runner 장르의 첫 샘플인 **Factory Runner**
(`GameSpecs/game01.json`)까지 구현되어 있습니다.

## 문서

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - 폴더 구조와 설계 원칙
- [docs/GAME_SPEC.md](docs/GAME_SPEC.md) - GameSpec JSON 필드 레퍼런스
- [docs/AUTOMATION.md](docs/AUTOMATION.md) - Editor 자동화 명령과 GitHub Actions 파이프라인
- [docs/BUILD.md](docs/BUILD.md) - Android 빌드/서명 방법
- [CLAUDE.md](CLAUDE.md) - Claude Code 작업 규칙 및 진행 상태

## 빠른 시작 (Unity Editor, Windows)

1. `ProjectSettings/ProjectVersion.txt`에 명시된 Unity 버전으로 프로젝트를 엽니다
   (설치된 버전이 다르면 이 파일의 버전 문자열만 실제 버전으로 맞추면 됩니다).
2. Unity 메뉴 `Game Factory > Generate > Factory Runner Sample` 실행
   → `Assets/GeneratedGames/game01/`에 Scene/Prefab이 생성됩니다.
3. 생성된 Scene을 열고 Play - 자동 이동/점프/중력반전/코인/장애물/게임오버/재시작이 동작해야 합니다.
4. `Game Factory > Validate > All GameSpecs`로 GameSpec/Scene 무결성을 확인합니다.
5. `Game Factory > Build > Factory Runner (APK)`로 APK를 빌드합니다 (`Builds/game01/APK/`).

CLI/CI로 동일한 작업을 수행하는 방법은 [docs/AUTOMATION.md](docs/AUTOMATION.md)를 참고하세요.

## 새 게임 추가하기

1. `GameSpecs/<game_id>.json`을 새로 작성합니다 (`docs/GAME_SPEC.md` 참고, `game.id`는 소문자
   snake_case로 유일해야 합니다).
2. 필요한 기믹이 `Assets/GameFactory/Modules/`에 이미 있다면 그대로 재사용합니다. 정말 새로운
   기믹일 때만 모듈을 추가합니다.
3. `GameFactoryGenerator.Generate("GameSpecs/<game_id>.json")`을 실행합니다 (메뉴 또는 CLI).
4. Validate → Test → Build 순으로 진행합니다.

캐릭터/배경만 바꾼 리스킨은 금지되어 있습니다 - `mechanics`/`level`/`enemy`/`special` 조합이 실제로
달라져야 새 게임으로 인정됩니다.

## 이 개발 환경(Claude Code 원격 컨테이너)의 한계

이 저장소에서 Claude Code로 작업하는 원격 컨테이너에는 Unity Editor가 설치되어 있지 않습니다.
C# 코드는 문법적으로 검토되지만, 실제 컴파일/Play 모드 실행/Android 빌드는 Unity가 설치된
Windows 환경(또는 self-hosted GitHub Actions runner)에서 처음으로 검증되어야 합니다.
