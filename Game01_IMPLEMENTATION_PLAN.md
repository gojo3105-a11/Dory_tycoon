# Game01_IMPLEMENTATION_PLAN.md - Factory Runner

`Game01_SCENARIO.md`를 실제로 구현하기 위한 상세 계획. 이 문서까지 완료된 뒤에만 코드/Scene 작업을
시작한다 (신규 지침의 단계 순서).

## 1. 구조 결정 (사용자 확인 완료)

**질문**: MainCharacter가 3D 휴머노이드인데 프로젝트 물리/카메라는 2D다 - 어떻게 가져갈까?
**답변(사용자 선택)**: **게임별로 유동적으로 결정한다.**

Game01은 평면 이동이 자연스러운 러너 장르이므로 **2D 물리/카메라를 그대로 유지**한다:

- `Rigidbody2D`/`Collider2D`/`Orthographic Camera` 그대로 사용 - 기존 `RunnerPlayerController`,
  `CameraFollow2D`, `GravitySwitchController` 등 전부 재사용, 재작성하지 않는다.
- `MainCharacter`는 **3D 메시(SkinnedMeshRenderer + Animator)를 2D 루트 오브젝트의 자식**으로 둔다.
  이동/충돌/중력 판정은 여전히 2D 컴포넌트가 담당하고, 3D 메시는 시각적 표현만 담당한다(Unity에서
  `Rigidbody2D`가 붙은 오브젝트의 자식에 3D `SkinnedMeshRenderer`를 두는 것은 기술적으로 문제 없음 -
  실제 충돌 판정용 `Collider2D`는 별도로 캐릭터 실루엣 크기에 맞춰 유지).
- 이 패턴은 Game03(퍼즐)/Game06(합치기)/Game10(슈팅)처럼 평면 이동이 자연스러운 게임에도 재사용
  가능하다. Game07(탐험)/Game08(운전)/Game09(서바이벌)처럼 자유 이동이 핵심인 게임은 별도로 3D
  물리·카메라를 도입할 예정(각 게임의 구현 계획에서 다시 다룸 - 지금 결정하지 않는다).

## 2. GameSpec / 게임 ID 정합성

기존 GameSpec은 `game.id = "factory_runner_001"`이고, 이미 이 id로 실제 APK 빌드·설치·동작까지
검증됐다(`PROJECT_ANALYSIS.md` §5). 신규 지침은 패키지 ID를 `com.gamefactory.game01`~`game10`으로
지정한다. `BundleIdUtility`는 `com.gamefactory.<game.id>`를 자동 생성하므로, 지금 이름을 정리하지
않으면 이후 9개 게임과 명명 규칙이 어긋난다.

**결정**: 아직 정식 배포(Play Store 등록 등)가 아니라 내부 검증 단계이므로, `GameSpecs/`의 파일과
`game.id`를 `factory_runner_001` → `game01`로 정리한다(파일 rename + 내부 id 변경 + 기존
`GeneratedGameManifest`/생성된 Scene·Prefab 경로도 함께 맞춤). CLAUDE.md의 "이미 배포된 게임의
bundle id는 안 바꾼다"는 규칙은 실제 배포 이후를 가리키므로 지금 시점 정리는 규칙 위반이 아니다.
이 작업은 실제 구현 단계에서 진행하고, 여기서는 계획만 명시한다.

- `GameSpecs/factory_runner_001.json` → `GameSpecs/game01.json` (`game.id: "game01"`, 다른 필드는
  유지)
- `GeneratedGames/factory_runner_001.json` 매니페스트는 새로 생성(3D 캐릭터 반영을 위해 Scene도
  다시 생성해야 하므로 기존 산출물을 그대로 옮기지 않는다)
- 문서(`docs/GAME_SPEC.md` 예시, `docs/BUILD.md`/`docs/AUTOMATION.md`의 커맨드 예시)의
  `factory_runner_001` 언급은 실제 코드 변경 시점에 함께 갱신

## 3. 재사용 vs 신규 작업

| 구성 요소 | 처리 |
|---|---|
| `Core/*` (GameManager, SaveSystem, PoolSystem, InputSystem, SceneController, AudioSystem, SettingsSystem) | 그대로 재사용 |
| `Gameplay/Runner/*` (이동/장애물/코인/중력존 스포너) | 그대로 재사용 |
| `Modules/GravitySwitch/*` | 그대로 재사용 |
| `CameraFollow2D` | 그대로 재사용 |
| `UI/GameUIController` | 확장 - 상점 화면 이벤트/상태 추가 (기존 GameManager 이벤트 구독 패턴 유지) |
| `Editor/*` 생성기 | `PrefabGenerator`가 MainCharacter 프리팹을 참조하도록 소폭 확장 (플레이어 프리팹을 코드로
  절차 생성하는 대신, 미리 만들어둔 `MainCharacter.prefab`을 인스턴스화하는 방식으로 변경) |
| MainCharacter 3D 모델/애니메이션 | **신규** - §4 |
| 상점(Shop) UI/데이터 | **신규** - 코인 자석, 스킨 1종 (시나리오 §6) |
| 환경/장애물 임시 프롭 | **신규(임시)** - §5 |

## 4. MainCharacter 통합 계획

- 저장 위치: `Assets/Common/Character/Prefabs/MainCharacter.prefab` (신규 지침이 지정한 경로,
  10개 게임 공용).
- 원본 이미지 저장 위치: `Assets/Common/Character/SourceImage/` - **아직 사용자가 이미지를 업로드하지
  않았으므로 폴더만 미리 만들어 두고, 업로드되면 그 파일을 절대 삭제/교체하지 않는다(신규 지침 원문
  규칙).**
- **임시 캐릭터 전략(이미지/3D 모델 확보 전 필수)**: Unity 기본 Capsule + 간단한 팔/다리 역할의
  Cube 자식 몇 개로 구성한 "박스 휴머노이드" placeholder를 `MainCharacter.prefab`으로 우선 등록한다.
  `Animator`는 Run/Jump 2개 상태만 가지는 최소 `AnimatorController`를 코드로 만든 애니메이션(위치
  이동 트윈 수준)으로 대체 - 실제 리깅된 애니메이션 클립이 없는 상태에서도 컴파일·실행이 가능해야
  한다.
- 실제 3D 모델이 확보되면(이미지 업로드 → 변환 도구 확인 → 실제 모델링, Phase 4에서 도구 자체를
  조사) 같은 프리팹 경로에서 캡슐 대신 실제 메시로 교체하고, 게임별 의상 변형은 자식 오브젝트의
  머티리얼/부착물 교체로 처리한다(신규 리깅 없이).
- **"3D 모델이 생성되지 않았는데 생성됐다고 보고하지 않는다"는 규칙에 따라, 이 단계 완료 보고에는
  반드시 "MainCharacter는 현재 임시 프리미티브이며 실제 3D 모델이 아님"을 명시한다.**

## 5. 환경/장애물 임시 에셋 계획

- 컨베이어 벨트: 기존 절차 생성 로직(`GroundSpawner`)이 만드는 2D 스프라이트를 유지하되, 색상을
  공장 테마에 맞게 조정(단색 placeholder 유지, 신규 텍스처 제작 없음).
- 장애물 3종(시나리오 §4): 기존 placeholder 스프라이트 생성 방식을 그대로 사용 - 신규 아트 없이
  형태(사각형/원형 등)와 색상만으로 구분.
- 이 항목들은 실제 아트가 확보되기 전까지 "핵심 게임플레이 우선 완성"이라는 신규 지침 원칙에 따라
  더 손대지 않는다.

## 6. UI 변경 사항

- `Shop` 화면 신규 추가: `SaveSystem`에 저장된 보유 코인/구매한 아이템 목록을 읽어 표시.
- `GameUIController`에 Shop 진입/이탈 이벤트 핸들러 추가(기존 GameOver 화면의 "상점" 버튼과 연결).
- 코인 자석 효과는 `RunnerPlayerController`가 장착 여부를 `SaveSystem`에서 읽어 반경 파라미터를
  적용하는 방식으로 구현(하드코딩 금지 - GameSpec이 아닌 세이브 데이터 기반 수치이므로 `Configure`류
  메서드로 런타임 주입).

## 7. QA 체크리스트 (신규 지침 Phase 8 반영)

APK 빌드 전 다음을 확인한다(실행은 Unity가 설치된 self-hosted runner에서, 이 원격 컨테이너는 문법
검토만 가능하다는 한계를 다시 명시):

- [ ] 컴파일 오류 0개 (Editor 콘솔/CI 로그 기준)
- [ ] Missing Script/Missing Reference 0개 (`GameValidator`가 이미 검사하는 항목 + 신규 Shop
      UI 요소도 포함되도록 검증 로직 점검)
- [ ] 핵심 루프 확인: 시작 → 점프/중력 전환 → 충돌 → 게임오버 → 재시작이 실제로 동작
- [ ] 상점에서 구매한 강화가 다음 판에 실제로 적용됨
- [ ] 기존 EditMode/PlayMode 테스트 통과 (Shop 관련 테스트는 필요 시 추가)

## 8. 빌드/리포트 산출물

- APK 출력: `Builds/Game01/Game01_FactoryRunner_v0.1.0.apk` (신규 지침 명명 규칙) - 기존
  `BuildAndroid.cs`의 출력 경로 규칙(`Builds/<gameId>/APK/<gameId>.apk`)과 다르므로, 이 명명
  규칙을 반영하려면 `BuildAndroid.cs`에 버전/표시용 이름을 위한 소폭 확장이 필요하다(게임 로직
  변경 아님, 파일명 조합 로직 추가).
- 패키지 ID: `com.gamefactory.game01` (§2의 id 정리 이후 자동 생성됨).
- 리포트: `Reports/Game01_Report.txt` - 게임 종류/게임 방법/게임 특징/조작방법/목표/성장요소/
  사용캐릭터/사용맵/APK 정보를 한국어 평문으로 작성(신규 지침 §10 필수 항목), **APK 파일이 실제로
  디스크에 존재하는 것을 확인한 뒤에만 작성한다.**

## 9. 작업 순서 (다음 실제 구현 단계)

1. `GameSpecs/game01.json` 정리(§2) + `docs/GAME_SPEC.md` 예시 갱신
2. `Assets/Common/Character/{Prefabs,SourceImage}/` 폴더 생성 + 임시 `MainCharacter.prefab`(§4)
3. `PrefabGenerator`가 MainCharacter 프리팹을 인스턴스화하도록 수정
4. Shop UI/데이터(§6) 추가
5. `BuildAndroid.cs`에 `GameXX_이름_v0.1.0.apk` 출력 명명 규칙 추가(§8)
6. self-hosted runner에서 파이프라인 실행 → APK 실존 확인
7. QA 체크리스트(§7) 통과 확인
8. `Reports/Game01_Report.txt` 작성
9. 위 전부(시나리오+계획+캐릭터+맵+핵심루프+컴파일오류0+APK 실존+리포트) 완료 후에만 Game02 착수
