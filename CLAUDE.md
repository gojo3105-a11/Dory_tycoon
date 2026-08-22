# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

이 저장소는 더 이상 "Dory Tycoon"(Godot) 프로젝트가 아니다.

이 저장소는 **Game Factory**다: Unity + Claude Code + GitHub Actions를 연결하여, 사람의 개입을 최소화하면서
Android 모바일 게임을 GameSpec 파일 하나로 자동 생성/테스트/빌드하는 시스템이다.

핵심 원칙: 게임마다 새로 코드를 짜지 않는다. 재사용 가능한 Core/Modules/Gameplay 코드와
GameSpec(JSON) 설정을 조합해서 게임을 "생성"한다.

```text
GameSpec(JSON) → Unity Editor 자동 생성기 → Scene/Prefab/Level/UI 생성
→ Validation → Unity Test → Android Build → APK/AAB
```

## Development Environment

- Engine: Unity (버전은 `ProjectSettings/ProjectVersion.txt` 참조, 임의 변경 금지)
- Language: C#
- Platform: Android (portrait 우선, iOS 확장 가능 구조 지향)
- Physics: 2D (Rigidbody2D / Collider2D)
- UI: uGUI (`UnityEngine.UI`), TextMeshPro 등 추가 패키지는 꼭 필요할 때만 도입
- CI/CD: GitHub Actions + Windows Self-hosted Runner (Unity 배치 모드 빌드)

## Project Structure

```text
Assets/
├─ GameFactory/
│  ├─ Core/            # 장르 무관 공용 시스템 (GameManager, SaveSystem, PoolSystem, InputSystem, ...)
│  │  └─ GameSpec/      # GameSpec 데이터 클래스 + 파서 + 밸리데이터
│  ├─ Gameplay/         # 장르별 게임플레이 코드 (Runner, Puzzle, Physics, Idle, Defense)
│  ├─ Modules/          # 재사용 가능한 기믹 모듈 (GravitySwitch, DoubleJump, Dash, ...)
│  ├─ UI/               # 게임 상태와 분리된 UI 컨트롤러
│  ├─ LevelGeneration/  # 절차적 레벨 생성
│  ├─ Editor/           # 자동 생성/검증/빌드 Editor 스크립트
│  ├─ Tests/            # EditMode / PlayMode 테스트
│  └─ Build/            # 빌드 자동화 관련 런타임/에디터 보조 코드
├─ Resources/           # GameSpec JSON이 런타임 참조용으로 복사되는 위치 (Resources/GameSpecs/<id>.json 등)
GameSpecs/               # 게임별 GameSpec 원본 JSON (예: factory_runner_001.json)
GeneratedGames/          # 생성기가 만들어낸 게임별 산출물 메타데이터
ProjectSettings/, Packages/   # Unity 표준 프로젝트 설정
Builds/                  # Android 빌드 산출물 (git에는 포함하지 않음, 폴더만 유지)
Logs/                    # 빌드/테스트/밸리데이션 로그 (git에는 포함하지 않음, 폴더만 유지)
.github/workflows/       # validate.yml, test.yml, build-android.yml, game-factory.yml
docs/                    # ARCHITECTURE.md, GAME_SPEC.md, AUTOMATION.md, BUILD.md
```

## GameSpec 구조

`GameSpecs/*.json` 하나가 게임 하나를 정의한다. JsonUtility로 파싱하므로 중첩 객체만 사용하고
Dictionary/다형성은 사용하지 않는다. 필드 정의는
`Assets/GameFactory/Core/GameSpec/GameSpecData.cs`가 단일 소스다.

```json
{
  "game": { "id": "factory_runner_001", "title": "Factory Runner", "genre": "Runner" },
  "player": { "moveSpeed": 6, "jumpPower": 10 },
  "mechanics": { "jump": true, "doubleJump": false, "dash": false, "gravitySwitch": true },
  "level": { "levelCount": 1, "difficulty": "Medium", "procedural": true, "length": 120 },
  "enemy": { "enabled": false, "types": 0 },
  "special": { "mechanic": "GravitySwitch" },
  "theme": { "environment": "Factory", "character": "Slime" }
}
```

- `game.id`는 lowercase snake_case 유일값이어야 한다 (`GameSpecValidator`가 검사).
- 새 필드를 추가할 때는 `GameSpecData.cs`, `GameSpecValidator.cs`, `docs/GAME_SPEC.md`를 함께 갱신한다.
- 구조적 검증(필드 형식)은 `GameSpecValidator`(Core), 파일 간 검증(중복 id, Bundle ID 충돌 등)은
  `Assets/GameFactory/Editor/GameValidator.cs`(예정)가 담당한다.

## 장르 / 모듈

1차 지원 장르: Runner, Puzzle, Physics (구조는 Idle, Defense, Merge, Arcade, Shooter까지 확장 가능하게 유지).

기믹은 `Assets/GameFactory/Modules/<ModuleName>/`에 독립 모듈로 구현한다. 새 게임은 기존 모듈을
조합해서 만들고, 정말 새로운 기믹일 때만 새 모듈을 추가한다. 캐릭터/배경만 바꾼 리스킨은 금지 —
GameSpec의 mechanics/level/enemy/special 조합이 실제로 달라져야 한다.

## Coding Rules

- Unity 최신 안정 API를 사용한다 (예: `Rigidbody2D.linearVelocity`, deprecated된 `velocity`는 쓰지 않는다).
- 타입 힌트/명시적 타입을 사용한다.
- 한 스크립트에 너무 많은 책임을 넣지 않는다. UI, 게임 상태(Core.GameManager), 캐릭터/기믹 상태를 분리한다.
- GameSpec에 있는 값은 하드코딩하지 않는다. 구조적 배선(에디터 타임)과 수치 튜닝(런타임 GameSpec 로드)을
  분리한다 — `SetReferences`/`SetTargets` 계열 메서드는 구조, `Configure` 계열 메서드는 수치.
- Singleton은 `GameManager`, `AudioManager` 등 정말 전역 상태가 필요한 곳에만 최소한으로 사용한다.
- Object Pooling(`Core/PoolSystem.cs`)을 사용해 Instantiate/Destroy로 인한 GC 스파이크를 피한다.
- Update()/FixedUpdate() 호출 수를 늘리지 않는다. 입력은 `Core/InputSystem.cs`의 `TapInput` 하나로 통일한다.
- 저사양 Android 기기 기준으로 성능을 고려한다 (Draw Call, Texture Size, 동시 오브젝트 수).

## 금지 사항

- 기존에 정상 동작하는 코드를 이유 없이 다시 작성하지 않는다.
- 대규모 파일 삭제를 피한다 (이미 삭제가 필요하면 반드시 먼저 사용자에게 확인한다).
- Unity `.meta` 파일을 임의로 삭제하지 않는다.
- `Library/`, `Temp/`, `Obj/` 등 Unity가 재생성하는 폴더는 git에 커밋하지 않는다 (`.gitignore` 참고).
- Keystore, 서명 비밀번호, API 키 등 민감 정보를 절대 커밋하지 않는다.
- Unity 버전을 임의로 올리거나 내리지 않는다 (`ProjectSettings/ProjectVersion.txt`는 실제 설치 버전과
  다르면 사용자가 직접 맞추거나 명시적으로 요청했을 때만 변경한다).
- 사용자의 허락 없이 커밋하거나 푸시하지 않는다.

## Unity Build / Test 방법

이 개발 환경(Claude Code 원격 컨테이너)에는 Unity Editor가 설치되어 있지 않다. 따라서:

- Unity Editor 실행, 컴파일 확인, Play 모드 테스트, 실제 Android 빌드는 **이 환경에서 직접 실행할 수 없다.**
- 대신 C# 문법을 수동으로 검토하고, 스크립트 간 참조(네임스페이스, 메서드 시그니처, 컴포넌트 이름)를
  꼼꼼히 맞춘 뒤 "실행하지 못했다"는 사실을 명확히 보고한다.
- 실제 컴파일/실행/빌드 검증은 Unity가 설치된 Windows 환경(또는 self-hosted GitHub Actions runner)에서
  수행되어야 한다. 명령 형태는 `docs/BUILD.md`, `docs/AUTOMATION.md` 참고.

## Git 규칙

- 작업 단위를 작게 나누어 커밋한다 (`feat: add game spec system`, `feat: add runner module` 등).
- 각 단계가 (문법적으로) 정상 동작할 때 커밋한다.
- 사용자의 허락 없이 커밋/푸시하지 않는다.

## Development Method

항상 다음 순서를 따른다.

1. 현재 파일 구조 분석
2. 구현 계획 제시 (사소한 선택은 스스로 판단, 아래 5가지 경우만 질문)
3. 최소 범위 구현
4. 가능한 범위에서 오류 검사 (Unity 미설치 시 수동 문법 검토로 대체하고 명시)
5. 변경 내용 요약 (아래 "결과 보고 방식" 형식)
6. 다음 작업 제안

질문이 필요한 경우는 다음 5가지뿐이다: 외부 계정/인증 정보, Unity 라이선스 문제, Android 서명 키 등
보안 정보, 기존 파일 대량 삭제, 복구하기 어려운 구조 변경. 그 외에는 가장 합리적이고 유지보수하기
쉬운 방법을 스스로 선택해서 진행한다.

## 결과 보고 방식

```text
현재 단계:
...

완료:
- ...

생성/수정 파일:
- ...

테스트 결과:
PASS / FAIL / 실행 불가 (사유)

다음 작업:
...
```

## 진행 상태 (Progress Log)

- [x] Phase 1: 저장소 분석 (Godot 프로젝트였음 → 초기화됨, Unity 프로젝트 없음 확인)
- [x] Phase 2: Game Factory 폴더 구조 생성
- [x] Phase 3: GameSpec JSON 시스템 (`GameSpecData`/`GameSpecParser`/`GameSpecValidator`)
- [x] Phase 4: Factory Runner MVP 코어 스크립트 (Core/Modules/Gameplay/UI)
- [ ] Phase 5: Unity Editor 자동 생성기 (GameFactoryGenerator/SceneGenerator/PrefabGenerator/LevelGenerator)
- [ ] Phase 6: Validation/Test 시스템 (GameValidator, Unity Test Framework)
- [ ] Phase 7: Android 커맨드라인 빌드 자동화 (BuildAndroid.cs)
- [ ] Phase 8: GitHub Actions 연결 (validate.yml/test.yml/build-android.yml/game-factory.yml)

이 목록이 실제 코드 상태와 항상 일치하도록, 각 Phase를 완료할 때마다 이 파일을 갱신한다.
