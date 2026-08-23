# Automation

## Editor 자동화 명령 (`-executeMethod`)

모든 명령은 Unity를 배치 모드로 실행해서 스크립트 하나를 호출하는 형태다.

**CI/CD에서는 Unity.exe를 직접 호출하지 않고, 반드시 `scripts/ci/wait-for-unity.ps1`을 통해서
실행한다.** Windows에서 Unity는 스스로 새 프로세스로 재실행하고 원래 프로세스는 먼저 종료되는
경우가 있어서, PowerShell이 그 원래 프로세스만 보고 "완료"로 착각하면 실제 작업(Scene 생성,
빌드 등)이 끝나기 전에 다음 단계로 넘어가 버린다 (실제로 self-hosted runner에서 겪은 문제 -
모든 단계가 몇 초 만에 "성공"으로 끝나는데 아무 산출물도 없었다). `wait-for-unity.ps1`은 이름이
"Unity"인 프로세스가 시스템에 하나도 남지 않을 때까지 기다린 다음, 실제 성공/실패를 판정한다:

- `-executeMethod` 기반 진입점(Generate/Validate/Build)은 `CommandLineExit.Exit(code, name)`을
  통해 `Logs/<name>.exitcode` 파일에 실제 종료 코드를 남긴다 - 스크립트가 그 파일을 읽는다.
- `-runTests` 기반(EditMode/PlayMode)은 Unity가 직접 제어하므로, `-testResults` XML의
  `result`/`failed` 속성을 대신 확인한다.

```powershell
.\scripts\ci\wait-for-unity.ps1 -SentinelName generate -UnityArgs @(
  '-batchmode', '-nographics', '-projectPath', '.',
  '-executeMethod', 'GameFactory.Editor.GameFactoryGenerator.GenerateFromCommandLine',
  '-gameSpec', 'GameSpecs/factory_runner_001.json',
  '-logFile', 'Logs/unity-generate.log'
)
exit $LASTEXITCODE
```

| 목적 | `-executeMethod` 대상 | 추가 인자 |
|---|---|---|
| GameSpec → Scene/Prefab 생성 | `GameFactory.Editor.GameFactoryGenerator.GenerateFromCommandLine` | `-gameSpec <path>` |
| 전체 GameSpec/Scene 검증 | `GameFactory.Editor.GameValidator.ValidateFromCommandLine` | 없음 |
| Android 빌드 | `GameFactory.Editor.BuildAndroid.BuildFromCommandLine` | `-gameId <id>`, `-buildType apk\|aab` |

Unity Test Framework는 별도 커맨드라인 플래그를 쓴다 (`-executeMethod`가 아님), 이때는
`-SentinelName` 대신 `-TestResultsPath`를 넘긴다:

```powershell
.\scripts\ci\wait-for-unity.ps1 -TestResultsPath 'Logs\unity-test-editmode.xml' -UnityArgs @(
  '-batchmode', '-nographics', '-projectPath', '.',
  '-runTests', '-testPlatform', 'EditMode',
  '-testResults', 'Logs/unity-test-editmode.xml',
  '-logFile', 'Logs/unity-test-editmode.log'
)
exit $LASTEXITCODE
```

`-testPlatform`을 `PlayMode`로 바꾸면 PlayMode 테스트가 실행된다. **PlayMode 테스트는 생성된
Scene(`Assets/GeneratedGames/<id>/Scenes/<id>.unity`)이 있어야 통과하므로, 항상 생성 단계
이후에 실행한다.**

Unity Editor 안에서 직접(대화형으로) 실행하려면 이 래퍼가 필요 없다 - `Game Factory` 메뉴를 쓴다:
`Generate > Factory Runner Sample`, `Validate > All GameSpecs`, `Build > Factory Runner (APK)`.

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

`scripts/windows-runner/`에 이 과정을 자동화하는 PowerShell 스크립트가 있다 (해당 Windows PC에서
관리자 권한으로 실행 - 이 저장소를 다루는 Claude Code 원격 컨테이너는 조직 네트워크 정책상 Unity
다운로드 서버에 접근할 수 없어서 여기서는 대신 실행할 수 없다). 순서와 각 단계 설명은
`scripts/windows-runner/README.md` 참고:

1. `01-install-unity-hub.ps1` - Unity Hub 설치
2. Unity Hub를 한 번 실행해서 Unity ID로 로그인하고 라이선스를 활성화한다 (수동, GUI, 이 머신에서
   최초 1회만).
3. `02-install-unity-editor.ps1 -Version <ProjectSettings/ProjectVersion.txt의 버전>` - Unity
   Editor + Android Build Support(OpenJDK/SDK/NDK 포함) 설치
4. `03-set-unity-path-env.ps1` - 워크플로우가 참조하는 `UNITY_PATH` 환경 변수를 자동으로 설정
5. `04-register-github-runner.ps1 -RepoUrl <저장소 URL> -Token <등록 토큰>` - GitHub Actions
   self-hosted runner를 다운로드/설정하고 Windows 서비스로 등록 (토큰은 저장소 Settings →
   Actions → Runners → New self-hosted runner에서 발급, 1시간 내 사용해야 함)

Play Store 서명이 필요하면 `docs/BUILD.md`의 시크릿 설정을 진행한다. 설정하지 않아도 파이프라인
자체는 Unity 기본 디버그 서명으로 끝까지 통과한다.

이 스크립트들은 실제 Windows 환경에서 검증된 적이 없다 - 각 파일 상단의 `.NOTES`에 Unity Hub
CLI 모듈명, GitHub runner 서비스 등록 명령 등 Hub/runner 버전에 따라 달라질 수 있는 부분과
대안을 적어두었다.

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
