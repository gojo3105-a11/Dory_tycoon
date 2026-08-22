# Automation

## Editor 자동화 명령 (`-executeMethod`)

모든 명령은 Unity를 배치 모드로 실행해서 스크립트 하나를 호출하는 형태다. Windows PowerShell
기준 예시 (self-hosted runner에서 그대로 쓰는 형태와 동일):

```powershell
& "$env:UNITY_PATH" -batchmode -nographics -projectPath . `
  -executeMethod GameFactory.Editor.GameFactoryGenerator.GenerateFromCommandLine `
  -gameSpec GameSpecs/factory_runner_001.json `
  -logFile Logs/unity-generate.log -quit
```

| 목적 | `-executeMethod` 대상 | 추가 인자 |
|---|---|---|
| GameSpec → Scene/Prefab 생성 | `GameFactory.Editor.GameFactoryGenerator.GenerateFromCommandLine` | `-gameSpec <path>` |
| 전체 GameSpec/Scene 검증 | `GameFactory.Editor.GameValidator.ValidateFromCommandLine` | 없음 |
| Android 빌드 | `GameFactory.Editor.BuildAndroid.BuildFromCommandLine` | `-gameId <id>`, `-buildType apk\|aab` |

세 메서드 모두 실패 시 `EditorApplication.Exit(1)`을 호출하므로, 호출하는 셸에서 `exit $LASTEXITCODE`
(PowerShell) 또는 `$?`(bash)로 그대로 CI 실패로 이어진다.

Unity Test Framework는 별도 커맨드라인 플래그를 쓴다 (`-executeMethod`가 아님):

```powershell
& "$env:UNITY_PATH" -batchmode -nographics -projectPath . `
  -runTests -testPlatform EditMode `
  -testResults Logs/unity-test-editmode.xml `
  -logFile Logs/unity-test-editmode.log
```

`-testPlatform`을 `PlayMode`로 바꾸면 PlayMode 테스트가 실행된다. **PlayMode 테스트는 생성된
Scene(`Assets/GeneratedGames/<id>/Scenes/<id>.unity`)이 있어야 통과하므로, 항상 생성 단계
이후에 실행한다.**

Unity Editor 안에서 직접 실행하려면 `Game Factory` 메뉴를 쓴다: `Generate > Factory Runner Sample`,
`Validate > All GameSpecs`, `Build > Factory Runner (APK)`.

## GitHub Actions 워크플로우

```text
.github/workflows/
├─ validate.yml       GameSpecs/** 변경 시: GameValidator만 실행
├─ test.yml           코드/스펙 변경 시: 생성 → EditMode/PlayMode 테스트
├─ build-android.yml  수동 실행(workflow_dispatch): 생성 → APK/AAB 빌드
└─ game-factory.yml   GameSpecs/** 변경 시: 생성 → 검증 → 테스트 → APK 빌드 (전체 파이프라인)
```

네 워크플로우 모두 `runs-on: [self-hosted, Windows]`이므로, Unity와 Android 빌드 도구가 설치된
Windows self-hosted runner가 최소 1대 등록되어 있어야 동작한다.

### Self-hosted runner 준비

1. Windows PC에 GitHub Actions self-hosted runner를 등록한다 (저장소 Settings → Actions →
   Runners → New self-hosted runner). 라벨은 기본값(`self-hosted`) + `Windows`로 충분하다.
2. Unity Hub로 `ProjectSettings/ProjectVersion.txt`에 명시된 버전을 설치하고, Android Build
   Support(OpenJDK + Android SDK/NDK 포함) 모듈을 함께 설치한다.
3. runner를 실행하는 계정(서비스 계정)의 환경 변수에 `UNITY_PATH`를 설정한다. 예:
   `C:\Program Files\Unity\Hub\Editor\6000.0.36f1\Editor\Unity.exe`
   (버전은 실제 설치 버전과 반드시 일치해야 한다.)
4. Play Store 서명이 필요하면 `docs/BUILD.md`의 시크릿 설정을 진행한다. 설정하지 않아도 파이프라인
   자체는 Unity 기본 디버그 서명으로 끝까지 통과한다.

### 각 워크플로우가 실패하면

- **validate.yml 실패**: `Logs/validation.log` 아티팩트를 확인한다. GameSpec 형식 오류, id/Bundle ID
  충돌, (Scene이 이미 생성되어 있다면) 필수 오브젝트/스크립트 누락 중 하나다.
- **test.yml 실패**: EditMode 실패는 순수 GameSpec 파싱/검증 로직 버그, PlayMode 실패는 생성된
  Scene의 실제 게임 동작(점수/게임오버/재시작) 문제일 가능성이 높다.
- **build-android.yml / game-factory.yml 빌드 단계 실패**: `Logs/unity-build.log`에 실패한
  BuildStep과 메시지가 남는다.

## 아직 자동화하지 않은 것

- 생성된 Scene/Prefab을 CI가 자동으로 커밋/PR 하지 않는다 - 지금은 사람이 로컬 Unity에서 생성
  결과를 리뷰하고 커밋하는 것을 기본 흐름으로 가정한다 (`docs/ARCHITECTURE.md` 참고).
- 여러 GameSpec을 한 번에 처리하는 배치 파이프라인은 없다 (한 워크플로우 실행 = 게임 하나).
