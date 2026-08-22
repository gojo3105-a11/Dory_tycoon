# Architecture

## 파이프라인

```text
GameSpecs/<id>.json
        │  GameSpecParser.LoadFromFile + GameSpecValidator.Validate
        ▼
GameFactoryGenerator.Generate(path)
        │
        ├─ PrefabGenerator   : Player/GroundTile/Obstacle/Coin/(GravityZone) 프리팹 생성
        ├─ SceneGenerator    : 프리팹 인스턴스화, 카메라/UI/GameManager 배선, Scene 저장
        └─ LevelGenerator    : GameSpec의 mechanics에 따라 기믹 스포너 배선
        │
        ▼
Assets/GeneratedGames/<id>/{Scenes,Prefabs}/*   (Unity가 인식하는 실제 에셋)
Assets/Resources/GameSpecs/<id>.json            (런타임 로드용 원본 스펙 복사본)
GeneratedGames/<id>.json                        (저장소 루트, 메타데이터: bundleId 등)
        │
        ▼
GameValidator.ValidateAll()   : 중복 id, Bundle ID 충돌, 필수 오브젝트/스크립트 누락 검사
        │
        ▼
Unity Test Framework (EditMode + PlayMode)
        │
        ▼
BuildAndroid.Build(id, apk|aab)   →  Builds/<id>/{APK,AAB}/<id>.{apk,aab}
```

## 폴더 구조와 책임

```text
Assets/
├─ GameFactory/
│  ├─ Core/          장르 무관 공용 시스템. Modules/Gameplay는 이 레이어에만 의존한다.
│  │  ├─ GameManager, SaveSystem, PoolSystem, InputSystem(TapInput),
│  │  │  SceneController, CameraFollow2D, AudioSystem, SettingsSystem
│  │  └─ GameSpec/   GameSpecData/Parser/Validator - GameSpec 스키마의 단일 소스
│  ├─ Gameplay/Runner/   Runner 장르 전용 게임플레이 (Player, 스포너들, UI 초기화)
│  ├─ Modules/GravitySwitch/   재사용 가능한 기믹 모듈 (다른 장르에서도 조합 가능)
│  ├─ UI/            GameUIController - GameManager 이벤트만 구독, 게임 상태를 직접 들고 있지 않음
│  ├─ Editor/         자동 생성/검증/빌드 도구 (Assembly-CSharp-Editor에만 컴파일됨)
│  ├─ Tests/          EditMode(순수 C#) / PlayMode(생성된 Scene 실행) 테스트
│  └─ Build/          (예약) 빌드 자동화 관련 런타임 보조 코드
├─ GeneratedGames/<id>/{Scenes,Prefabs}/   생성기 산출물 (Unity 에셋 - git에 포함)
└─ Resources/GameSpecs/<id>.json           런타임에서 Resources.Load로 읽는 스펙 사본

GameSpecs/<id>.json     게임별 원본 스펙 (사람이 작성/수정)
GeneratedGames/<id>.json   생성기/빌드가 기록하는 메타데이터 (bundleId 등, Unity 에셋 아님)
```

Editor/ 밑의 스크립트는 Unity 컴파일 규칙상 자동으로 Editor 전용 어셈블리로 분리되므로,
런타임 코드(Core/Gameplay/Modules/UI)가 Editor 코드를 참조하는 일은 절대 없어야 한다 (반대는 가능).

## 설계 원칙

- **구조 vs 수치 분리**: `SetReferences`/`SetTargets` 계열 메서드는 에디터 타임에 오브젝트 참조를
  배선한다 (SceneGenerator가 호출). `Configure` 계열 메서드는 GameSpec에서 온 수치를 적용한다
  (Runner의 경우 런타임에 `RunnerGameInitializer`가 `Resources/GameSpecs/<id>.json`을 읽어 호출).
  같은 값을 두 곳에서 서로 다르게 설정하는 일이 없도록, 각 값은 정확히 한 곳에서만 설정한다.
- **Object Pooling**: `Core/PoolSystem.cs`의 `GameObjectPool`을 모든 스포너(Ground/Obstacle/Coin/
  GravityZone)가 공유한다. `RecycleWhenPassed`가 플레이어 X좌표 기준으로 자동 반납한다.
- **입력 통일**: 모든 탭/클릭 입력은 `Core/InputSystem.cs`의 `TapInput.Tapped` 정적 이벤트 하나로
  들어온다. Update() 호출을 늘리지 않기 위해서다.
- **Singleton 최소화**: `GameManager`, `AudioManager`만 싱글턴이다. 둘 다 씬 하나에 인스턴스가
  하나뿐이어야 하는 전역 상태(점수/게임오버 상태, 공유 SFX 소스)를 가진다.
- **플레이스홀더 아트**: `PrefabGenerator`가 게임 id를 시드로 한 단색 스프라이트를 절차적으로
  생성한다 (실제 아트가 준비되면 같은 경로의 파일만 교체하면 됨 - 생성 코드는 손댈 필요 없음).
- **하나의 Unity 프로젝트, 여러 게임**: 여러 게임의 GeneratedGames/가 같은 프로젝트에 누적될 수
  있지만, `BuildAndroid`는 항상 지정된 게임 **하나의 Scene만** 포함해서 빌드한다 (전체 게임이
  한 APK에 합쳐지지 않는다).

## 아직 없는 것 (알려진 한계)

- Puzzle/Physics/Idle/Defense 등 다른 장르의 SceneGenerator/PrefabGenerator는 아직 없다
  (`GameFactoryGenerator`는 `genre != Runner`면 예외를 던진다).
- GravitySwitch 외의 Modules(DoubleJump, Dash, MovingPlatform 등) 폴더는 비어 있다 - 실제로
  필요해지는 다음 게임에서 구현한다.
- CI에서 생성된 Scene/Prefab을 자동으로 커밋하지 않는다 (의도적 - 아직 사람이 검토 없이 저장소에
  커밋을 남기지 않도록). `Assets/GeneratedGames/`는 git에 포함되는 실제 에셋이므로, 사람이 로컬
  Unity에서 생성 후 리뷰하고 커밋하는 것을 기본 흐름으로 가정한다.
