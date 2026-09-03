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

## 역할 분담 (2026-09-02 사용자 지시, 이후 모든 작업에 적용)

세 가지가 고정 규칙이다. 편해서가 아니라 사용자가 정한 것이므로 지킨다.

1. **모든 코딩은 Codex에게 요청한다.** Claude는 명세를 `AI_GAME_COMPANY/config/TASKBOARD.json`에
   올리고, 나온 diff를 리뷰하고, 설정/문서를 관리한다. 프로덕션 코드를 직접 쓰지 않는다.
   정책 키는 `codex_writes_all_code`.
2. **디자인이 필요하면 Gemini에 요청한다** (무료 등급). 정책 키는 `allow_gemini_design`,
   키는 `GEMINI_API_KEY` 환경변수. 아래 제약을 반드시 지킨다.
3. **관제 화면은 AI를 회사 부서별 캐릭터로 보여준다** (`docs/OFFICE_VIEW_SPEC.md`).

**규칙 1의 예외 기록.** 사용자가 직접 지시한 경우에만 Claude가 코드를 썼다: 2026-09-03 "두 가지 사항은
너가 직접 고치기"(진행 상황 한글 요약, 작업 대기열 → CODEX-LIVE1까지 함께 종결), 같은 날 "전체 문제 있는
부분 및 디자인과 개발시스템 수정"(CODEX-RUNLOG1, CODEX-BOARD1, sync-and-run.ps1 상태 파일, 한국어
작업 제목). 각 작업판 항목의 notes에 "DONE BY CLAUDE"로 남겨두었다. 그 외에는 규칙 1이 그대로다.

**여기서 반드시 알아야 하는 현실 하나:** `codex` CLI는 빌드 PC에만 있고 **Claude Code
컨테이너에는 없다** (`which codex` → 없음). 그래서 규칙 1을 지키면 Claude는 이 환경에서
**작업을 큐에 넣는 것까지만** 할 수 있고, PC에서 `orchestrator team run --task <id>`를
돌려야 실제 코드가 생긴다. 이 지연은 규칙의 대가이지 버그가 아니다 -
"Codex에게 맡겼다"고 말한 뒤 코드가 저장소에 없으면, 아직 실행되지 않은 것이다.

### Gemini 제약 (코드로 강제할 것, 문서만으로는 부족)

- **별도 환경변수 `GEMINI_API_KEY`.** `GOOGLE_API_KEY`는 `blocked_env_keys`에 그대로 둔다 -
  이 프로젝트의 다른 코드가 구글 키를 조용히 쓰기 시작하는 일이 없어야 한다.
- **무료 모델만.** `gemini_free_tier_models`에 없는 모델 id는 어댑터가 거부한다.
- **429/쿼터 소진 시 절대 승격하지 않는다.** `on_codex_limit`과 같은 방식으로 degrade한다.
- **키는 절대 커밋/로그/출력하지 않는다.** 존재 여부만 기록한다. 로그인은 HUMAN_GATE
  (`initial_gemini_login`).
- Google 공식 요금 페이지(`ai.google.dev`)는 이 환경의 egress 프록시에서 차단된다. 즉
  무료 등급을 1차 출처로 확인한 것이 아니다 - 그러니 **가정하지 말고 실패하게** 만든다.

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
GameSpecs/               # 게임별 GameSpec 원본 JSON (예: game01.json)
                         # + .ci-trigger (JSON 아님, GameValidator가 무시함 - CI 트리거 전용, 아래 참고)
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
  "game": { "id": "game01", "title": "Factory Runner", "genre": "Runner" },
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

### 컴파일 에러를 직접 확인하는 방법 (사용자에게 물어보기 전에 먼저 여기를 본다)

사용자 PC가 `scripts/dev/collect-errors.ps1`로 Unity 로그에서 에러를 뽑아
**`Reports/errors/latest.txt`**에 커밋한다 (자동 동기화가 15분마다 실행). 이 파일에는 컴파일
에러, CS0618 obsolete 경고, 런타임 예외가 들어 있다.

**빌드(APK/AAB)가 실제로 만들어졌는지도 같은 방식으로 확인한다.** `Builds/<gameId>/`에 생긴 실제
파일을 `scripts/dev/report-build-status.ps1`이 스캔해서 **`Reports/build-status/latest.txt`**에
커밋한다(같은 자동 동기화 주기). GitHub Actions API 접근이 없어도 이 파일 하나로 "APK가 실제로
디스크에 있는지"를 확인할 수 있다 - CLAUDE.md 최상단 원칙("APK가 생성되지 않았는데 성공했다고
보고하지 않는다")을 지키려면 이 파일을 반드시 먼저 확인한다.

**중요 - 작업 디렉터리가 두 개다.** self-hosted runner는 `C:\Dory_tycoon`(사용자가 Unity Editor로
직접 만지는 클론)을 쓰지 않는다. GitHub Actions runner는 자기 `_work` 폴더에 따로 체크아웃하며,
이 프로젝트에서는 **`C:\actions-runner\_work\Dory_tycoon\Dory_tycoon`**이다. 두 리포트 스크립트는
이제 양쪽을 모두 스캔한다(`-CiWorkspacePath` 파라미터). 이걸 몰라서 CI가 계속 실패하는데도 리포트에는
아무것도 안 잡히는 상태로 17시간을 흘려보낸 적이 있다 - 리포트가 "갱신 안 됨"이면 스크립트가 엉뚱한
폴더를 보고 있는 게 아닌지 먼저 의심한다. 두 폴더를 정션으로 합치지는 않는다: `actions/checkout`이
매 실행마다 `git clean`을 돌려서 `C:\Dory_tycoon`의 커밋 안 된 작업을 날려버린다.

**새 Unity 내장 모듈 API를 쓰면 `Packages/manifest.json`에 그 모듈을 추가해야 한다.** 이 프로젝트는
내장 모듈을 의도적으로 최소한만 켜둔다(androidjni, audio, particlesystem, physics2d, ui). 예를 들어
`UnityEngine.ParticleSystem`을 쓰기 시작했을 때 `com.unity.modules.particlesystem`을 안 넣어서
`CS1069: The type name 'ParticleSystem' could not be found` 컴파일 에러로 파이프라인이 죽었다.
`packages-lock.json`은 손으로 고치지 말고 Unity가 재생성하게 둔다.

또한 `GameFactory.Editor.asmdef`가 `GameFactory.Runtime`을 참조하므로, **Runtime 쪽 컴파일이 깨지면
Editor 쪽 파일은 아예 컴파일되지 않아 에러 목록에 나타나지도 않는다.** Runtime 에러를 먼저 고치고
다시 확인해야 Editor 에러가 보인다 - 에러 목록이 짧다고 문제가 그것뿐이라고 단정하지 않는다.

**오케스트레이터 실행 결과와 자동 동기화 상태도 같은 방식이다** (2026-09-03 추가). 두 파일이 더 있다:

- **`Reports/runs/latest.txt`** - `python -m company.orchestrator.main <명령>`을 실행할 때마다
  `company/orchestrator/runlog.py`가 남긴다(`serve` 제외). 명령, 종료 코드, 소요 시간, 출력 꼬리,
  예외. `Reports/runs/<시각>-<명령>.txt`로 최근 50개 보관. `blocked_env_keys`와 `GEMINI_API_KEY`의
  **값**은 쓰기 전에 `[REDACTED:<이름>]`으로 치환된다 - 이름만 남는다. 기록 실패는 stderr에만 찍히고
  명령의 종료 코드를 바꾸지 않는다.
- **`Reports/sync-status/latest.txt`** - `scripts/desktop/sync-and-run.ps1`이 매 실행마다 쓴다.
  `Outcome`은 OK / UP-TO-DATE / BLOCKED / FAILED, `Reason`에 이유. 결과가 바뀌었거나 6시간이 지났을
  때만 커밋한다(15분마다 타임스탬프만 바뀌는 커밋을 하루 96개 만들지 않기 위해). 이 파일이 7시간 넘게
  갱신되지 않으면 예약 작업 자체가 죽은 것이다.

이 두 파일이 생긴 이유: 2026-09-03 아침, 자동 동기화가 추적 파일 하나가 더러워진 것 때문에 8시간 동안
아무것도 머지하지 않았는데, 그 사실이 gitignore된 `Logs/auto-sync.log`에만 남아서 아무도 몰랐다. 그리고
같은 날 `team run` 실패 세 건을 사용자가 콘솔에서 복사해 붙여야 했다. **"pull 하세요" / "에러 붙여주세요"를
말하기 전에 이 파일들을 먼저 읽는다.** 대시보드의 "PC 연결" 섹션이 같은 두 파일을 보여준다.

`sync-and-run.ps1`은 `Packages/packages-lock.json`이 수정돼 있으면 Unity가 다시 쓴 것으로 보고
housekeeping 커밋을 만든 뒤 진행한다(`ProjectVersion.txt`와 같은 취급). 다른 추적 파일이 더러우면 여전히
멈추고, 그 사실을 `sync-status`에 BLOCKED로 남긴다.

이 저장소(`gojo3105-a11/Dory_tycoon`)에는 그 파일들이 사용자가 병합할 때까지 안 들어올 수
있으므로, 최신 상태는 **사용자 포크에서 직접 읽는다**:

```bash
git fetch https://github.com/gojo3105/dory_tycoon claude/delete-current-content-mgn4xm:fork-check
git show fork-check:Reports/errors/latest.txt
git show fork-check:Reports/build-status/latest.txt
git show fork-check:Reports/sync-status/latest.txt
git show fork-check:Reports/runs/latest.txt
git branch -D fork-check
```

파일이 없거나 오래되었으면(생성 시각 확인) 그때 사용자에게 요청한다. **"에러 있으면 붙여주세요"나
"APK 확인해주세요"를 먼저 말하지 말고, 위 방법으로 먼저 확인한다.**

## 연동된 AI 현황 보기 / 제어 (관제 화면)

```bash
python -m company.orchestrator.main dashboard --open   # 읽기용 HTML 파일
python -m company.orchestrator.main serve              # 제어판 (버튼이 실제로 실행됨)
```

`dashboard`는 `Reports/dashboard.html`을 만든다. 커밋된 파일만 읽으므로 빌드 PC에서든
Unity가 없는 컨테이너에서든 같은 답을 낸다. 이미지(게임 아트 / AI 생성물 / 캐릭터 원본)는
data URI로 파일 안에 박아 넣으므로, 그 한 파일만 있으면 어디서든 보인다.

**PC에서는 `scripts/desktop/open-control-panel.ps1` 하나로 연다** - upstream을 당기고(sync-and-run.ps1
`-NoTrigger`), `AI_GAME_COMPANY/`로 들어가 `serve`를 띄우고, 브라우저를 연다. `company` 패키지가
`AI_GAME_COMPANY/` 안에 있어서 저장소 루트에서 `serve`를 치면 `No module named 'company'`로 죽는데,
그걸 매번 기억하지 않게 하려는 스크립트다.

`serve`는 같은 화면에 실행 버튼을 붙여서 `http://127.0.0.1:8765` 로 띄운다.
Codex 작업 실행 / 빌드 / Codex 진단 / 변경 파일 확인을 브라우저에서 누를 수 있다.
**정적 파일 쪽에는 버튼이 아예 안 나온다** - 누를 곳이 없는 버튼은 없는 게 낫다.

`server.py`가 위험한 파일이라 네 가지를 코드로 강제한다:

- **127.0.0.1 전용.** `0.0.0.0`으로 바꾸면 빌드 실행 엔드포인트가 랜에 열린다.
- **명령은 클라이언트에서 오지 않는다.** 브라우저는 동작 *이름*만 보내고 argv는
  `server.py`가 만든다. `shell=False`, 그리고 게임/작업 id는 `^[A-Za-z0-9][\w-]{0,63}$`
  통과 + 실제 파일/작업판 존재 확인을 둘 다 해야 한다.
- **토큰.** localhost는 경계가 아니다 - 브라우저의 어떤 페이지든 여기로 POST할 수 있어서,
  실행마다 새로 만드는 랜덤 토큰과 Origin 검사로 막는다.
- **한 번에 한 작업.** Unity 빌드와 Codex 실행이 같은 작업 트리를 쓴다.

커밋/푸시는 여기서도 하지 않는다.

이 화면의 원칙은 하나다: **근거가 없으면 "확인 불가"로 표시하고, 절대 "정상"으로 올려
읽지 않는다.** 각 AI 줄마다 그 상태를 읽어온 파일을 함께 보여준다. "설치됨"은 근거가
아니다 - 라이선스 미확인 + RAM 초과로 못 돌아가는 모델도 설치는 되어 있다.

## PC 원격 제어 (pc-control.yml) - Claude가 PC에서 명령을 돌리는 유일한 길

2026-09-03 사용자 지시("너가 직접 돌려. 안되면 방법 찾아서 실행해")로 만들었다. Claude Code 컨테이너는
PC에 닿을 수 없고, 포크에는 이 세션의 자격 증명이 없다(403). 유일하게 되는 길은 **gojo3105-a11에 등록된
self-hosted 러너에게 워크플로를 보내는 것**이다. `.github/workflows/pc-control.yml`이 그 채널이다.

- 러너 조건: PC에 **두 번째 러너**를 `C:\actions-runner-control`에 설치, **라벨 `pc-control`**, 그리고
  **NETWORK SERVICE가 아니라 사용자 계정으로 실행**(`04-register-github-runner.ps1 -WindowsLogonAccount`).
  서비스 계정은 `C:\Dory_tycoon`, 포크용 git 자격 증명, Codex 로그인 중 어느 것도 갖고 있지 않다.
- 기존 4개 빌드 워크플로에는 `if: github.repository_owner != 'gojo3105-a11'`이 붙어 있다. 러너가 생기면
  그 워크플로들이 upstream에서도 돌기 시작해 같은 PC에서 Unity 빌드 두 개가 겹치기 때문이다. **CI 빌드는 포크,
  upstream 러너는 제어 채널.** 이 둘을 섞지 않는다.
- 동작은 `status / sync / dashboard / team-run / codex-doctor` 다섯 개로 고정. 입력이 명령이 되는 경로는 없고,
  task id는 server.py의 SAFE_ID와 같은 패턴으로 검사한 뒤에만 argv에 들어간다.
- **`status`가 기본이고 아무것도 건드리지 않는다.** `stash_dirty`는 별도 opt-in이며, `status` 결과를 읽어
  무엇이 stash되는지 본 뒤에만 켠다. 삭제는 절대 없다 - stash는 `git stash list`로 복구된다.
- 결과 읽기: `mcp__github__get_job_logs`로 이 세션에서 직접 읽는다. 사용자가 붙여넣을 필요가 없다.

## Codex와 함께 개발하기 (공유 작업판)

Codex는 리뷰어가 아니라 **공동 개발자**다. `AI_GAME_COMPANY/config/TASKBOARD.json`이
Claude와 Codex가 함께 보는 작업판이고, 각 작업에는 `owner`(claude/codex)와
`files`(수정 허용 파일 목록)가 있다.

```bash
python -m company.orchestrator.main team board                 # 누가 뭘 하는지
python -m company.orchestrator.main team run --task CODEX-ART1 --dry-run   # 보낼 프롬프트만 확인
python -m company.orchestrator.main team run --task CODEX-ART1            # Codex가 실제로 코드를 작성
```

`AI_GAME_COMPANY/` 안에서 실행한다. Codex는 `codex exec --sandbox workspace-write`로
돌아가므로 편집 범위가 저장소 안으로 제한되고, 실행이 끝나면 `git status` 기준으로
**실제 변경된 파일이 그 작업의 허용 목록 안인지** 검사한다. 벗어나면 상태가 BLOCKED가
되고 **아무것도 되돌리지 않는다** — 같은 작업 트리에 다른 쪽의 미커밋 작업이 있을 수
있어서, 조용히 버리는 쪽이 더 위험하다.

세 가지는 코드로 강제된다 (`company/orchestrator/teamwork.py`):

- **allow_codex_write** 정책이 true여야 쓰기가 열린다. `use_codex_subscription`만으로는
  리뷰만 가능하다 (게이트가 두 개인 이유: 리뷰어를 켜는 것과 공동 개발자를 켜는 것은
  다른 결정이다).
- **커밋/푸시는 절대 하지 않는다.** 작업 트리에 변경만 남기고, 사람이 검토 후 커밋한다.
- **상태는 DONE이 아니라 REVIEW가 된다.** 여기서 컴파일한 게 없기 때문이다. DONE은
  `orchestrator build`가 통과한 뒤에 사람이 정한다.

Codex는 이 프로젝트를 기억하지 못한 채 매번 시작하므로, CLAUDE.md의 핵심 규칙
(linearVelocity, Editor/Runtime 분리, .ps1 ASCII, 커밋 금지 등)이 프롬프트에 자동으로
붙어서 전달된다 — `teamwork.HOUSE_RULES`가 그 원문이다. 규칙을 바꾸면 거기도 같이 고친다.

## PowerShell 스크립트 규칙

`scripts/**/*.ps1`는 **ASCII만 사용한다 (한글 금지).** Windows PowerShell 5.1은 BOM 없는 UTF-8
`.ps1`을 로컬 코드페이지로 읽어서 한글 문자열 리터럴이 깨지고, 심하면 파싱 자체가 실패한다
(실제로 겪은 문제 - `collect-errors.ps1`/`sync-and-run.ps1`이 이것 때문에 실행되지 않았다).
사용자에게 보여줄 한국어 설명은 `.md` 문서에 쓴다 (문서는 실행되지 않으므로 안전하다).

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

**2026-09-03 사용자 지시: "항상 결과 요약하고 쉽게 말해."** 모든 답변은 결론 한 줄로 시작한다.
전문 용어 대신 쉬운 말을 쓰고, 명령은 복사해서 붙일 수 있게 한 덩어리로 준다. 긴 설명은 결론 뒤에 둔다.


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
- [x] Phase 5: Unity Editor 자동 생성기 (GameFactoryGenerator/SceneGenerator/PrefabGenerator/LevelGenerator)
- [x] Phase 6: Validation/Test 시스템 (GameValidator, Unity Test Framework EditMode/PlayMode)
- [x] Phase 7: Android 커맨드라인 빌드 자동화 (BuildAndroid.cs)
- [x] Phase 8: GitHub Actions 연결 (validate.yml/test.yml/build-android.yml/game-factory.yml)
- [x] 문서화: README.md, docs/ARCHITECTURE.md, docs/GAME_SPEC.md, docs/AUTOMATION.md, docs/BUILD.md

이 목록이 실제 코드 상태와 항상 일치하도록, 각 Phase를 완료할 때마다 이 파일을 갱신한다.

## 10개 게임 프로젝트 진행 상태

`GAME_10_MASTER_PLAN.md` 기준 10개 게임 전체 기획 완료, 순차 개발 진행 중(한 번에 한 게임만).

- [x] Phase 0-1: `PROJECT_ANALYSIS.md`, `GAME_10_MASTER_PLAN.md`
- [x] Game01 (Factory Runner): 시나리오/구현계획/캐릭터(임시)/맵/핵심루프/상점/컴파일 오류 0개/
      APK 빌드 확인(`game-factory-game01` 아티팩트, self-hosted runner)/`Reports/Game01_Report.txt`
      전부 완료 - **Game01 완료.**
- [ ] Game02 (Idle Factory Tycoon): 아직 시작 안 함. `Game02_SCENARIO.md`부터 순서대로.
- [ ] Game03~10: 미착수.

## 다음으로 할 만한 작업 (미구현/알려진 한계)

- Puzzle/Physics 등 다른 장르의 Scene/PrefabGenerator가 없다 (Runner만 구현됨) - Game02(Idle)부터는
  새 장르용 생성기가 필요하다.
- GravitySwitch 외 Modules(DoubleJump, Dash, MovingPlatform 등)는 폴더만 있고 비어 있다.
- self-hosted Windows runner 등록 및 실제 빌드 파이프라인 실행이 검증됨(Game01 APK 빌드 성공) -
  `TagManager.asset` 직접 조작, `PlayerSettings.Android` 서명 API,
  `PrefabUtility.InstantiatePrefab(Object, Scene)` 오버로드 등 이전에 "확인 불가능"으로
  표시했던 API들도 실제로 컴파일/실행되는 것을 확인했다.
- `Assets/Common/Character/Prefabs/MainCharacter.prefab`은 아직 실제 3D 모델이 아니라
  Unity 프리미티브 임시 placeholder다 (`Assets/Common/Character/CHARACTER_DESIGN.md` 참고) -
  실제 3D 모델 확보/변환 도구 조사는 여전히 미착수.
