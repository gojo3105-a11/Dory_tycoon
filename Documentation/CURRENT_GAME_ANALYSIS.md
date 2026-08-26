# Current Game Analysis

대상: `gojo3105-a11/Dory_tycoon`, 브랜치 `claude/delete-current-content-mgn4xm`, Game01(Factory Runner,
`GameSpecs/game01.json`). 작성일 2026-08-26. Unity/Android 빌드 자체는 실제 CI에서 검증됐지만
(`Reports/Game01_Report.txt`, `game-factory-game01` 아티팩트 16.4MB), **이 문서의 그래픽/UI/Game
Feel 평가는 코드를 읽고 판단한 것이며 실제 화면을 직접 본 것이 아니다 - NOT VERIFIED로 표시한 항목은
문자 그대로 눈으로 확인하지 못했다는 뜻이다.**

## 좋은 부분

- GameSpec(JSON) → Editor 생성기 → Validate → Test(EditMode/PlayMode) → Build 파이프라인이
  self-hosted runner에서 실제로 끝까지 통과해 설치 가능한 APK를 만들어낸다 - "돌아간다"가 아니라
  "빌드까지 자동화됐다"는 뜻에서 Game Factory의 핵심 전제가 검증됨.
- `Core`(장르 무관) / `Gameplay/Runner`(장르 전용) / `Editor`(생성기) / `UI` 폴더 분리가
  일관되게 지켜지고 있다 - 새 장르 추가 시 `Core`를 건드릴 필요가 없는 구조.
- `SetReferences`(에디터 타임 구조 배선)와 `Configure`(런타임 GameSpec 수치 적용)가 모든
  스포너/컨트롤러에서 예외 없이 분리되어 있다 - CLAUDE.md 원칙이 실제로 지켜짐.
- `PoolSystem.GameObjectPool`을 Ground/Obstacle/Coin 스포너가 전부 사용 - Instantiate/Destroy
  GC 스파이크 없음.
- `CameraFollow2D`는 `Vector3.SmoothDamp` 기반 - 카메라가 딱딱하게 순간이동하지 않고 부드럽게
  따라간다(당초 이 분석 초안에서 "카메라 스무딩 없음"이라고 잘못 짐작했다가 코드를 다시 읽고
  정정함 - 검증 없이 판단하지 않는다는 원칙을 스스로 지킨 사례로 남겨둔다).
- `MainCharacter` 공유 프리팹 구조가 이미 잡혀 있다 - 실제 3D 모델로 교체해도 게임 로직은 전혀
  손댈 필요가 없다(§13 캐릭터 시스템 요구사항과 방향이 일치).
- `SaveSystem`이 `<gameId>.<key>` 형식으로 네임스페이스 분리되어 있어 여러 게임이 한 기기를
  공유해도 세이브가 충돌하지 않는다.
- Update()/FixedUpdate()/LateUpdate() 호출이 전체 코드베이스에 9곳뿐이고 각각 목적이 명확하다
  (입력 폴링 1곳, 카메라 1곳, 스포너 4곳, 재활용 판정 1곳, 플레이어 물리 1곳, Safe Area 재계산 1곳
  [TASK-003, 씬당 1개 인스턴스뿐이고 실제 변경 시에만 재계산]) - God Object 없음, 모든
  MonoBehaviour가 100줄 미만.

## 퀄리티가 낮은 부분

- 캐릭터가 Unity Capsule/Sphere/Cylinder/Cube 조합의 단색 placeholder다(§16이 명시적으로 금지하는
  Default Capsule/Default Material을 그대로 사용 중).
- 지형/장애물/코인/중력존이 전부 절차 생성된 단색 스프라이트다 - 실제 아트 0건.
- 사운드가 전혀 재생되지 않는다 - `AudioManager.PlaySfx`/`SettingsSystem.SoundEnabled`가 코드에는
  있지만 어떤 게임플레이 코드도 호출하지 않는다(grep으로 확인 - 정의부 외에는 참조 0건).
- Particle/VFX가 전혀 없다 - 코인 획득, 중력 전환, 충돌 어디에도 시각 효과가 없다.
- Camera Shake, Hit Stop, Impact 연출, Button Feedback, Screen Transition 등 Game Feel 요소가
  전부 없음(§21 목록 기준 0/13 구현).
- Vibration/Haptic 피드백 없음(코드 전체에서 `Handheld.Vibrate` 참조 0건).
- Main Menu가 없다 - `GameManager.Start()`가 씬 로드 즉시 `StartGame()`을 호출해 바로 게임플레이로
  들어간다. "Play 버튼을 누른다"는 동작 자체가 존재하지 않는다(§17 Vertical Slice 필수 항목 중
  Main Menu/Play Button 미충족).
- UI가 전부 Unity 기본 `Text`/`Button`/`Image`에 단색 배경이다 - Safe Area 처리 없음, 폰트는
  `LegacyRuntime.ttf` 하나뿐, 화면 전환 애니메이션 없음(패널이 `SetActive(true/false)`로 즉시
  나타났다 사라짐).

## 반드시 유지할 시스템

- `GameSpecParser`/`GameSpecValidator`/`GameSpecData` - JSON 기반 게임 정의 스키마, 신규 장르
  추가 시에도 그대로 확장.
- `GameFactoryGenerator`/`SceneGenerator`/`PrefabGenerator`/`LevelGenerator` - 생성 파이프라인
  자체(내부 구현은 이번 개선 대상이지만 구조는 유지).
- `GameManager`/`SaveSystem`/`PoolSystem`/`SceneController`/`InputSystem(TapInput)` - 장르 무관
  Core, 실제로 잘 동작 확인됨.
- `BuildAndroid`/`GameValidator`/`CommandLineExit`/`scripts/ci/wait-for-unity.ps1` - CI 빌드
  자동화 전체. Windows에서 Unity 프로세스 재실행 문제 등 실전에서 겪은 버그가 이미 다 고쳐진
  상태라 다시 만들 이유가 없음.
- `Assets/Common/Character/Prefabs/MainCharacter.prefab` 구조(메시만 교체 대상, 계층 구조와
  `MainCharacterSkin` 연동 방식은 유지).
- `ShopKeys`/`SaveSystem` 기반 화폐·구매 패턴 - 아이템이 늘어나도 재사용 가능.

## 수정해야 할 시스템

- `AudioManager` - 정의만 있고 미사용. `Coin.Collect()`/`RunnerPlayerController.HandleTap()`
  (점프)/`GameManager.TriggerGameOver()` 최소 3곳에 실제 SFX 재생을 연결해야 한다.
- `MainCharacterSkin` - 지금은 "빨간 스킨 1종을 material.color로 덮어쓰기"라는 임시 방식이다.
  실제 스킨이 여러 개 생기면 Material/Mesh 교체 방식으로 일반화해야 한다(§13 Equipment/Skin
  구조에 맞춰서).
- `ShopController` - 아이템 2개를 각각 `HandleCoinMagnetClicked`/`HandleRedSkinClicked`로 하드
  코딩했다. 게임마다 상점 아이템이 늘어나면 데이터 기반(리스트+아이템 정의) 구조로 바꿔야 확장이
  된다 - 지금 당장은 아이템이 2개뿐이라 동작에는 문제 없음, P2로 분류.
- `SceneGenerator.BuildUI` - Main Menu가 없는 구조 자체를 바꿔야 한다(§17 요구사항).

## 삭제해야 할 임시 요소

- `PrefabGenerator.CreateSolidSprite`가 만드는 단색 스프라이트(지형/장애물/코인/중력존) - 실제
  아트로 교체 시 삭제 대상.
- `MainCharacterGenerator`가 만드는 캡슐형 placeholder 메시 - 실제 3D 모델 도입 시 삭제 대상
  (단, 프리팹 자체와 `MainCharacterSkin`은 유지).

## 그래픽 문제

- Default Cube/Sphere/Capsule/Cylinder 사용 중 (§16 정면 위반, 지금은 "Prototype 단계"로 간주하고
  있었으나 새 기준으로는 Vertical Slice 검수 전에 반드시 교체해야 하는 대상).
- Material이 `Unlit/Color` 단색뿐 - 조명/그림자/텍스처 없음.
- 배경이 단색 카메라 클리어 컬러 하나뿐 - 패럴랙스/원경 없음.
- 아트 스타일이라고 부를 만한 것이 없음(전부 단색 도형) - 이 항목은 "스타일 불일치"가 아니라
  "스타일 자체가 없음"이 정확한 진단이다.

## UI 문제

- Safe Area 처리 없음 - `CanvasScaler`만 있고 노치/펀치홀 기기에서 UI가 잘릴 위험이 실재한다
  (구체적 버그 가능성으로, 실제 기기 테스트 전까지 NOT VERIFIED).
- Unity 기본 `Button`/`Text`, 폰트 1종, 버튼 터치 피드백(눌림 애니메이션 등) 없음.
- 화면 전환이 즉시 SetActive 방식 - 트랜지션 애니메이션 없음.
- 버튼 크기가 GameSpec/디자인 문서 기준으로 정해진 게 아니라 임의 픽셀값(`280x90` 등)이라 실제
  모바일 터치 타겟 크기 가이드라인(대략 최소 88x88dp 이상 권장)을 만족하는지 검증되지 않음.

## 게임성 문제

- 조작이 탭(점프) 하나뿐이고 기믹도 중력 전환 1개뿐 - 반복 플레이를 지탱할 만한 "재미있는 선택"이
  부족하다(예: 속도 조절, 다른 조작 옵션, 위험-보상 트레이드오프 없음).
- 난이도 곡선이 거리에 비례한 선형 증가 하나뿐 - 실제 플레이테스트로 튜닝된 적이 없다.
- 상점 아이템 2개가 성장 요소의 전부 - 반복 방문 동기가 약함.

## 코드 구조 문제

- `RecycleWhenPassed.Update()`가 풀링된 오브젝트 하나하나마다 개별적으로 거리 계산을 수행한다 -
  지금 오브젝트 수(십여 개)에서는 성능 문제가 아니지만, 스포너 하나가 중앙에서 일괄 처리하는
  구조가 아니라는 점에서 "Update 남용 방지" 원칙과는 결이 다르다. 지금 당장 고칠 필요는 없음(P2).
- `MainCharacterSkin`이 자식 오브젝트를 `transform.Find("Body")`/`"Head"`라는 문자열로 찾는다 -
  `MainCharacterGenerator`가 만드는 이름과 정확히 일치해야 하는 암묵적 결합이다. 지금은 두 파일이
  바로 옆에 있어 위험이 낮지만, 실제 3D 모델 교체 시 이름이 달라지면 조용히 실패할 수 있다(P2).
- ScriptableObject를 전혀 사용하지 않는다 - 대신 GameSpec(JSON)이 그 역할을 하고 있어 원칙 위반은
  아니지만, 상점 아이템/장애물 종류처럼 "게임 하나 안에서 여러 개 나열되는 데이터"는
  ScriptableObject가 더 적합할 수 있다(§12 검토 대상, P2).

## 성능 문제

- 코드상으로는 확인된 성능 문제 없음(풀링 사용, Update 호출 수 적음, Dynamic Batching은 사용자가
  직접 껐음 - `PROJECT_ANALYSIS.md` 참고).
- 실제 기기(특히 저사양 Android)에서의 프레임/발열 측정은 **NOT VERIFIED** - 이 환경과 CI 모두
  실기기 프로파일링 수단이 없다.

## 개선 우선순위

**P0 = 반드시 수정 (Vertical Slice 통과 조건)**
1. Main Menu + Play 버튼 추가 (지금은 씬 로드 즉시 게임플레이 시작 - §17 필수 항목 미충족)
2. 캐릭터 실제 그래픽 확보 또는 최소한 Primitive가 아닌 스타일화된 대체(§16)
3. 지형/장애물/코인 최소한의 실제 그래픽(단색 스프라이트 탈피)
4. 점프/코인/충돌 SFX 3종 연결 (`AudioManager`는 이미 있음 - 호출만 추가하면 됨)
5. Safe Area 대응 (실기기 노치/펀치홀 UI 잘림 위험 제거)

**P1 = 중요한 개선**
1. 코인 획득/중력 전환 Particle, 충돌 시 Camera Shake/Hit Stop
2. 버튼 터치 피드백 + 화면 전환 애니메이션
3. Vibration 피드백(점프/충돌)
4. 게임오버 화면 → 결과 화면 재설계(§17 "결과 화면" 항목에 맞춰 Retry/Home 명확화 - 지금도
   Restart는 있지만 "Home"에 해당하는 타이틀 복귀 동선이 없음, Main Menu 자체가 없으므로 P0
   1번과 연동)

**P2 = 추가 개선**
1. `ShopController` 데이터 기반 구조로 일반화
2. `MainCharacterSkin` 문자열 기반 결합을 더 안전한 방식으로
3. 난이도 곡선 실측 튜닝
4. `RecycleWhenPassed` 개별 Update 구조 재검토(현재 규모에서는 불필요)

## P0 Task 목록 (§18 형식)

### TASK-001 Main Menu + Scene Flow
- 목표: 씬 로드 즉시 게임플레이가 시작되는 현재 구조를 Title → Play 입력 → 게임플레이 → 결과 →
  (Retry/Home) 흐름으로 바꾼다. 별도 Scene을 새로 만들지 않고 한 Scene 안에서 Canvas 패널
  전환으로 구현한다(멀티 Scene 로딩은 지금 규모에 과함 - CLAUDE.md 과잉 설계 금지 원칙).
- 수정 파일: `GameManager.cs`(즉시 `StartGame()` 호출 제거, `GameState.Ready`에서 대기하도록),
  `SceneGenerator.cs`(Title 패널 + Play 버튼 추가), `GameUIController.cs`(Title 표시/숨김 연동)
- 신규 파일: 없음(기존 UI 생성 패턴 재사용)
- 의존성: 없음(가장 먼저 진행 가능, 모든 P0 중 유일하게 외부 에셋 불필요)
- 완료 조건: Scene 로드 시 게임플레이가 자동 시작되지 않고 Title 패널이 먼저 보인다. Play를
  눌러야 `StartGame()`이 호출된다. 게임오버 후 결과 화면에서 Home을 누르면 Title로 돌아간다.
- 테스트 방법: PC에서 `compile-check.ps1` 통과 확인 → Unity Editor Play 모드로 직접 눌러보고
  Title→Play→게임오버→Home→Title 순환이 실제로 되는지 확인(이 원격 환경은 Play 모드 확인 불가,
  PC 확인 필수 - NOT VERIFIED 상태로 보고).
- **구현 상태: 코드 구현 완료, 커밋/푸시 완료 (`c220fb1`).** PlayMode 테스트도 새 플로우에 맞게
  갱신함(`GameStartsOnTitleScreenInReadyState`가 `Ready` 상태를 검증, 나머지 테스트는
  `StartGame()`을 먼저 호출). Unity Editor Play 모드 실측(NOT VERIFIED)만 PC 확인 대기 중.

### TASK-002 최소 SFX 연결 (점프/코인/충돌)
- 목표: `AudioManager`(이미 구현됨, 미사용 상태)를 실제로 호출해 점프/코인 획득/충돌 3가지
  이벤트에 소리가 나게 한다.
- 에셋 문제: 라이선스 있는 SFX 파일이 이 프로젝트에 없다(§15 우선순위 1~4 전부 미충족). §15
  5순위("자체 제작 가능한 단순 보조 요소")에 따라 `AudioClip.Create` + 코드로 생성한 짧은
  사인파 톤(삐/딩/퉁 수준)을 임시로 사용한다 - 실제 SFX가 아니라 절차 생성 placeholder라는 점을
  명시하고, 나중에 실제 사운드로 교체할 지점을 분리해둔다.
- 수정 파일: `RunnerPlayerController.cs`(점프 시), `Coin.cs`(획득 시), `GameManager.cs`(게임오버 시)
- 신규 파일: `Assets/GameFactory/Core/ProceduralTone.cs`(사인파 AudioClip 생성 유틸)
- 의존성: 없음
- 완료 조건: 3개 이벤트 각각에서 `AudioManager.Instance.PlaySfx(...)` 호출이 실행된다.
  `SettingsSystem.SoundEnabled`가 false면 재생되지 않는다.
- 테스트 방법: PC Play 모드에서 소리가 실제로 나는지 확인 (NOT VERIFIED 상태로 보고 예정 -
  이 환경은 오디오 재생 확인 불가).
- **구현 상태: 코드 구현 완료, 커밋/푸시 완료 (`157db13`).** `ProceduralTone.Sine`으로 사인파
  생성, `AudioManager.PlaySfx`에 `SettingsSystem.SoundEnabled` 게이트 추가, 씬에 없던
  AudioManager+AudioSource를 `SceneGenerator`가 새로 생성하도록 수정(기존엔 아예 인스턴스가
  없어 무음이었음). 실제 재생음 청취(NOT VERIFIED)만 PC 확인 대기 중.

### TASK-003 Safe Area 대응
- 목표: 노치/펀치홀 기기에서 UI가 잘리지 않도록 모든 UI 패널을 Safe Area 안쪽으로 앵커링한다.
- 수정 파일: `SceneGenerator.cs`(Canvas 루트 아래 SafeArea 컨테이너 추가, 기존 패널들을 그 안으로)
- 신규 파일: `Assets/GameFactory/UI/SafeAreaFitter.cs`(`Screen.safeArea` 기반 RectTransform 조정,
  런타임에 해상도/노치가 바뀌어도 재계산)
- 의존성: 없음(TASK-001과 독립적으로 진행 가능)
- 완료 조건: `SafeAreaFitter`가 Canvas 하위 모든 UI의 부모가 되고, `Screen.safeArea` 값으로
  anchorMin/Max를 계산한다.
- 테스트 방법: 코드 검토로 로직 확인(실제 노치 기기 시뮬레이션은 Unity Editor의 Device Simulator
  필요 - NOT VERIFIED, PC 확인 필요).
- **구현 상태: 코드 구현 완료, 커밋/푸시 완료 (`6095094`).** HUD/GameOverPanel/ShopPanel/
  TitlePanel 전부 새 `SafeArea` 컨테이너 하위로 옮김. Device Simulator 실측(NOT VERIFIED)만
  PC 확인 대기 중.

## P0 완료 요약

TASK-001/002/003 세 가지 모두 코드 구현·커밋·푸시 완료. TASK-004/005(실제 3D 모델/환경 아트)는
§15/§43에 따라 여전히 보류 상태 - 라이선스 있는 에셋이나 image-to-3D 도구를 사용자가 지정하기
전까지는 시작하지 않는다. 세 TASK 모두 Unity Editor Play 모드/Device Simulator 실측은 이
원격 환경에서 불가능하므로 NOT VERIFIED로 남아 있고, PC 쪽 `compile-check.ps1` 통과 확인과
실제 Play 모드 확인이 필요하다.

## P1 Task 목록

### TASK-006 Particle + Camera Shake + Hit Stop
- 목표: 코인 획득/중력 전환에 파티클, 장애물 충돌 시 카메라 셰이크 + 짧은 Hit Stop.
- 수정 파일: `CameraFollow2D.cs`(`Shake()` 추가), `RunnerPlayerController.cs`(`Die()`에서
  셰이크+HitStop 트리거), `GameManager.cs`(`Awake()`에서 `Time.timeScale` 무조건 리셋 - HitStop
  코루틴이 씬 리로드로 중간에 끊겨도 다음 씬이 슬로모션에 갇히지 않도록), `Coin.cs`,
  `PrefabGenerator.cs`(GravitySwitch 사용 시 Player에 `GravitySwitchVfx` 부착),
  `SceneGenerator.cs`(`VfxManager` 생성)
- 신규 파일: `Assets/GameFactory/Core/VfxManager.cs`(재사용되는 단일 ParticleSystem - 풀링된
  코인/장애물에 파티클을 자식으로 붙이면 `GameObjectPool.Release()`가 즉시 `SetActive(false)`해서
  파티클이 보이기도 전에 꺼지므로, 씬 루트에 고정해두고 위치만 옮겨 `Emit()`하는 방식으로 회피),
  `Assets/GameFactory/Modules/GravitySwitch/GravitySwitchVfx.cs`(중력 전환 이벤트 구독)
- 의존성: 없음(외부 에셋 불필요, Unity 내장 ParticleSystem만 사용)
- 완료 조건: 장애물 충돌 시 카메라가 흔들리고 짧게 슬로모션이 걸린다. 코인 획득/중력 전환 시
  파티클이 실제로 보인다.
- 테스트 방법: PC Play 모드 실측 필요(NOT VERIFIED, 특히 타이밍/강도 같은 "Feel"은 코드 리뷰만으로
  판단 불가).
- **구현 상태: 코드 구현 완료, 커밋/푸시 완료 (`f1466d5`).**

### TASK-007 Vibration 피드백 (점프/충돌)
- 목표: 점프/장애물 충돌 시 `Handheld.Vibrate()` 호출.
- 수정 파일: `SettingsSystem.cs`(`VibrationEnabled` 추가, `SoundEnabled`와 동일 패턴),
  `RunnerPlayerController.cs`
- 신규 파일: 없음
- 의존성: 없음
- 완료 조건: 점프/충돌 시 진동이 발생한다. `SettingsSystem.VibrationEnabled`가 false면 발생하지 않는다.
- 테스트 방법: 실기기 필요(에디터에서는 `Handheld.Vibrate()`가 no-op) - NOT VERIFIED.
- **구현 상태: 코드 구현 완료, 커밋/푸시 완료 (`c086852`).**

### TASK-008 버튼 터치 피드백 + 패널 전환 애니메이션
- 목표: 버튼이 눌렸을 때 스케일 피드백, 패널(GameOverPanel/ShopPanel/TitlePanel) 전환이 즉시
  `SetActive`가 아니라 페이드로 보이게 한다.
- 수정 파일: `SceneGenerator.cs`(모든 버튼에 `ButtonPunchFeedback` 부착, 세 패널에
  `CanvasGroup`+`PanelTransition` 부착), `GameUIController.cs`/`ShopController.cs`
  (`SetActive(true/false)` → `PanelTransition.Show()/Hide()`, 씬 로드 시 최초 상태 설정 라인은
  애니메이션 없이 그대로 유지)
- 신규 파일: `Assets/GameFactory/UI/ButtonPunchFeedback.cs`(눌림 시 스케일 축소 후 원복),
  `Assets/GameFactory/UI/PanelTransition.cs`(`CanvasGroup.alpha` 코루틴 페이드)
- 의존성: 없음
- 완료 조건: 버튼을 누르면 살짝 작아졌다 돌아온다. 패널이 즉시 나타나지 않고 페이드 인/아웃된다.
- 테스트 방법: PC Play 모드 실측 필요(NOT VERIFIED, 타이밍/Feel은 코드 리뷰만으로 판단 불가).
- **구현 상태: 코드 구현 완료, 커밋/푸시 완료.**

### TASK-004 / TASK-005 (환경 그래픽, 캐릭터 그래픽) - 보류
현재 이 원격 환경과 PC 양쪽 모두 실제 아트 에셋도, 라이선스 있는 무료 에셋 소스도, 이미지→3D
변환 도구도 연결되어 있지 않다(§14/§15 기준 재확인 - 이전 세션에서 이미 조사한 결론과 동일).
**존재하지 않는 아트 에셋을 만들었다고 보고하지 않는다.** 이 두 Task는:
1. 필요한 작업을 여기에 명확히 기록해뒀고(단색 스프라이트 → 실제 텍스처/스프라이트,
   Primitive 캐릭터 → 실제 3D 모델),
2. 임시 요소(단색 스프라이트/캡슐 캐릭터)를 계속 사용하며,
3. 교체 지점은 이미 분리되어 있다(`PrefabGenerator.CreateSolidSprite`,
   `MainCharacterGenerator`/`Assets/Common/Character/`).
사용자가 실제 사용 가능한 에셋 소스(무료 라이선스 팩, 3D 변환 서비스 등)를 알려주기 전까지는
착수하지 않는다 - 임의로 유료 서비스를 쓰거나 라이선스 불명 에셋을 가져오지 않는다(§15/§43).

## Vertical Slice 재정의

§17 기준으로 Game01을 다시 보면, "코드가 존재한다"와 "Vertical Slice 통과"는 다른 이야기다.
현재 Game01은 핵심 Gameplay/승리(엔드리스라 승리 개념은 없음, 최고 기록 갱신으로 대체)/실패/조작은
갖췄지만, Main Menu/Sound/VFX/Animation/제대로 된 결과 화면이 빠져 있다. **다음 작업은 Game01을
새 게임(Game02)으로 넘어가기 전에, 이 P0 목록을 완료해서 실제 Vertical Slice 기준을 통과시키는
것이다.**
