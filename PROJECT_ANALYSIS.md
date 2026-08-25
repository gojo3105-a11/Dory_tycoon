# PROJECT_ANALYSIS.md

10개 모바일 게임 제작을 시작하기 전, 현재까지 검증된 Unity/Android 빌드 환경을 분석한 기록이다.
날짜: 2026-08-23. 이 문서는 이후 실제 값이 확인될 때마다 갱신한다 (특히 "확인 필요" 표시된 항목).

## 1. Unity 버전

- **6000.5.9f1** (Unity 6.5)
- `ProjectSettings/ProjectVersion.txt`에 고정되어 있음
- self-hosted 빌드 PC(Windows 11)에 Unity Hub로 설치되어 있고, Unity Personal 라이선스로 활성화됨
- **주의**: 애초 이 프로젝트를 시작할 때 버전을 `6000.0.36f1`로 추정해서 넣었으나 실제 존재하지 않는
  버전이라 빌드가 실패했다. PC에 실제로 설치되어 있던 `6000.5.9f1`로 맞춘 뒤부터 정상 동작했다.
  **앞으로 이 프로젝트의 Unity 버전을 임의로 바꾸지 않는다.**

## 2. 렌더 파이프라인

- **Built-in Render Pipeline** (URP/HDRP 패키지를 추가한 적 없음)
- 지금까지 만든 콘텐츠(Factory Runner)는 2D Sprite + Orthographic Camera만 쓰므로 렌더 파이프라인
  차이가 실질적으로 드러난 적은 없다.
- **3D 캐릭터/환경을 도입하면 이 부분을 다시 검토해야 한다** — Built-in RP로 계속 갈지, URP로
  전환할지는 3D 에셋의 실제 요구사항(Shader 호환성, 모바일 성능)을 보고 결정한다. 이유 없이 지금
  바꾸지 않는다.

## 3. Android Build Support

- Unity Hub에서 Unity 6.5(6000.5.9f1)에 **Android Build Support 설치 확인됨** (OpenJDK, Android
  SDK/NDK Tools 포함, Package Manager 콘솔 오류 없음으로 재확인)
- 실제 Android Player 빌드가 self-hosted runner에서 **성공** (`Build Finished, Result: Success.`)

## 4. 현재 프로젝트 구조

```text
Assets/
├─ GameFactory/
│  ├─ GameFactory.Runtime.asmdef   # Core/Gameplay/Modules/UI 전체를 묶는 런타임 어셈블리
│  ├─ Core/            GameManager, SaveSystem, PoolSystem, InputSystem(TapInput),
│  │                   SceneController, CameraFollow2D, AudioSystem, SettingsSystem
│  │  └─ GameSpec/      GameSpecData/Parser/Validator
│  ├─ Gameplay/Runner/  Runner 장르 게임플레이 (현재 유일하게 구현된 장르)
│  ├─ Modules/GravitySwitch/   재사용 가능 기믹 모듈
│  ├─ UI/               GameUIController
│  ├─ Editor/            GameFactory.Editor.asmdef - 자동 생성/검증/빌드 도구
│  │                    (GameFactoryGenerator, PrefabGenerator, SceneGenerator,
│  │                     LevelGenerator, GameValidator, BuildAndroid, ...)
│  └─ Tests/
│     ├─ EditMode/       GameFactory.Tests.EditMode.asmdef (순수 NUnit)
│     └─ PlayMode/       GameFactory.Tests.PlayMode.asmdef (생성된 Scene 실행)
├─ GeneratedGames/<id>/{Scenes,Prefabs}/   생성기 산출물 (Unity 에셋)
└─ Resources/GameSpecs/<id>.json

GameSpecs/<id>.json        게임별 원본 스펙 (JSON)
GeneratedGames/<id>.json   생성/빌드 메타데이터 (bundleId 등, Unity 에셋 아님)
scripts/
├─ ci/wait-for-unity.ps1          CI에서 Unity 배치 실행을 안전하게 기다리는 래퍼
├─ windows-runner/                self-hosted runner 최초 설치 스크립트
└─ desktop/                       바탕화면 아이콘으로 파이프라인 원격 실행
.github/workflows/          validate.yml, test.yml, build-android.yml, game-factory.yml
```

이 구조는 "GameSpec(JSON) 하나 → Scene/Prefab 자동 생성 → Validate → Test → Build" 파이프라인을
위해 설계되었다 (`docs/ARCHITECTURE.md` 참고). 지금까지 만들어진 콘텐츠는 전부 2D이고, 캐릭터/맵은
절차적으로 생성된 단색 placeholder 스프라이트다 (실제 아트/3D 모델 없음).

## 5. TEST APK 빌드 방식

1. GitHub Actions self-hosted runner (Windows PC, `run.cmd`로 대화형 실행 중 - 서비스 모드는
   NetworkService 계정 문제로 보류, `docs/AUTOMATION.md`/`scripts/windows-runner/README.md` 참고)
2. `.github/workflows/game-factory.yml`이 순서대로 실행:
   Generate(`GameFactoryGenerator.GenerateFromCommandLine`) → Validate(`GameValidator`) →
   Test EditMode → Test PlayMode → Build(`BuildAndroid.BuildFromCommandLine`)
3. 각 Unity 배치 실행은 `scripts/ci/wait-for-unity.ps1`을 거친다 - Windows에서 Unity.exe가 스스로
   재실행하면서 원래 프로세스가 먼저 종료되는 문제 때문에, 직접 `& $unity ...`로 호출하는 대신 이
   래퍼가 "이 실행이 띄운 Unity 프로세스가 전부 종료될 때까지" 능동적으로 기다린 뒤 진짜 결과
   (성공/실패)를 판정한다.
4. **현재 상태 (재확인 완료)**: 로그 파일 경로 충돌 버그(`unity-build-report.log` 분리)를 수정한 뒤
   재실행한 파이프라인에서 실제로 설치 가능한 APK가 정상 생성되었고, 사용자가 직접 기기에 설치해
   정상 동작을 확인했다. **Generate → Validate → Test(EditMode/PlayMode) → Build 5단계 파이프라인이
   self-hosted Windows runner에서 끝까지 통과해 유효한 APK를 만들어내는 것이 실전 확인되었다.**
   이제부터 10개 게임 제작은 이 검증된 파이프라인을 기반으로 진행한다.

## 6. 사용 중인 Unity Packages (`Packages/manifest.json`)

```json
{
  "com.unity.modules.androidjni": "1.0.0",
  "com.unity.modules.audio": "1.0.0",
  "com.unity.modules.physics2d": "1.0.0",
  "com.unity.modules.ui": "1.0.0",
  "com.unity.test-framework": "1.4.5",
  "com.unity.ugui": "2.5.0"
}
```

- **`Packages/packages-lock.json` 확보 완료(PC에서 커밋).** Unity 6.5가 실제로 리졸브한 버전:
  `com.unity.ugui 2.5.0`, `com.unity.test-framework 1.7.0`(선언은 1.4.5지만 상위 호환 버전으로
  리졸브됨), `com.unity.ext.nunit 2.1.0`, 나머지 모듈은 전부 `1.0.0`.
- TextMeshPro, Input System(신규), URP/HDRP, Cinemachine, Addressables 등은 **미설치**.

## 7. Input System

- **레거시 Input Manager** (`UnityEngine.Input` - `Input.GetMouseButtonDown`, `Input.touchCount`)
- 신규 Input System 패키지(`com.unity.inputsystem`)는 사용하지 않음
- `Core/InputSystem.cs`의 `TapInput`이 마우스 클릭과 터치를 하나의 이벤트(`TapInput.Tapped`)로
  통일해서 제공한다

## 8. UI 시스템

- **uGUI (레거시)**: `UnityEngine.UI.Text`, `Button`, `Canvas`, `CanvasScaler`, `GraphicRaycaster`
- TextMeshPro는 사용하지 않음 (의존성 최소화를 위해 의도적으로 제외)
- `UI/GameUIController.cs`가 유일한 UI 컨트롤러 - GameManager 이벤트만 구독, 게임 상태를 직접
  들고 있지 않음

## 9. 카메라 시스템

- `Core/CameraFollow2D.cs` - 2D 전용, X/Y 축 개별 추적 여부를 설정 가능한 범용 컴포넌트
- 현재는 Orthographic 2D 카메라만 사용 (3D 게임을 만들려면 새 카메라 시스템이 필요하다)

## 10. 저장 시스템

- `Core/SaveSystem.cs` - `PlayerPrefs` 기반, 게임 id로 키를 네임스페이스 분리 (`<gameId>.best_score` 등)
- 클라우드 저장, 외부 DB 등은 없음

## 11. Android 설정

| 항목 | 값 | 비고 |
|---|---|---|
| Package Name | `com.gamefactory.<game_id>` | `BundleIdUtility`가 자동 생성, `GeneratedGames/<id>.json`에 기록되어 재빌드해도 변경되지 않음 |
| Minimum API Level | Unity 6.5 기본값 | **명시적으로 지정한 적 없음 - 확인 필요** |
| Target API Level | Unity 6.5 기본값 | **명시적으로 지정한 적 없음 - 확인 필요** |
| Orientation | Portrait 고정 | `BuildAndroid.cs`가 빌드 시 설정 |
| Version | `bundleVersion`/`bundleVersionCode` | 비어 있을 때만 `1.0.0`/`1`로 초기화, 이후 유지 |
| 서명 | Unity 기본 디버그 서명 | `ANDROID_KEYSTORE_PATH` 등 환경변수 미설정 - Play Store 배포용 서명 아님 (`docs/BUILD.md`) |

## 12. Gradle 설정

- Unity가 기본 제공하는 Gradle 템플릿을 그대로 사용 (`mainTemplate.gradle`, `gradleTemplate.properties`
  등을 커스터마이즈한 적 없음)
- 별도 Gradle 버전 고정/커스텀 설정 없음

## 13. 현재 정상 빌드 설정 (요약 - 유지해야 할 것)

- Unity **6000.5.9f1**, Android Build Support 포함
- self-hosted Windows runner, **대화형(`run.cmd`) 실행** (서비스 모드는 미해결 이슈로 보류)
- `UNITY_PATH` 환경 변수가 위 Unity 설치를 가리킴
- `scripts/ci/wait-for-unity.ps1` 래퍼를 통한 모든 Unity 배치 실행
- `Packages/manifest.json` + Package Manager로 리졸브된 uGUI/Test Framework 버전
- `GameFactory.Runtime` / `GameFactory.Editor` / `GameFactory.Tests.EditMode` /
  `GameFactory.Tests.PlayMode` 4개 asmdef 구조

**10개 게임 제작 중 이 설정들을 이유 없이 바꾸지 않는다.** 3D 캐릭터/맵 도입으로 인해 정말
필요한 변경(예: 렌더 파이프라인, 새 패키지 추가)만 최소한으로 한다.

## 14. 다음에 확인이 필요한 항목

- Android Minimum/Target API Level 실제 값 (Player Settings에서 확인)
- 3D 캐릭터/환경 에셋을 도입할 경우 필요한 추가 패키지(예: 애니메이션 리타게팅, glTF 임포터 등)와
  Image-to-3D 변환에 실제로 쓸 수 있는 도구가 이 환경(원격 컨테이너 + PC)에 있는지 - **아직
  조사 전, Phase 4에서 확인한다.**

~~파이프라인 5단계 최종 재확인~~ - **완료.** 사용자가 실제 기기에서 APK 정상 설치/동작을 확인함.
