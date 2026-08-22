# Build

## 로컬에서 빌드하기 (Unity Editor)

1. `Game Factory > Generate > Factory Runner Sample` (또는 원하는 GameSpec에 대해
   `GameFactoryGenerator.Generate("GameSpecs/<id>.json")`)로 Scene을 먼저 생성한다.
2. `Game Factory > Build > Factory Runner (APK)`를 실행한다.
3. 결과물은 `Builds/<game_id>/APK/<game_id>.apk` (또는 AAB 빌드 시 `Builds/<game_id>/AAB/`)에
   생성된다. 빌드 로그는 `Logs/unity-build.log`.

## CLI로 빌드하기

```powershell
& "$env:UNITY_PATH" -batchmode -nographics -projectPath . `
  -executeMethod GameFactory.Editor.BuildAndroid.BuildFromCommandLine `
  -gameId factory_runner_001 -buildType apk `
  -logFile Logs/unity-build.log -quit
```

`-buildType`을 `aab`로 바꾸면 Google Play 제출용 App Bundle이 생성된다. 빌드 대상 Scene
(`Assets/GeneratedGames/<id>/Scenes/<id>.unity`)이 없으면 즉시 예외를 던지고 실패한다 - 먼저
`GameFactoryGenerator`를 실행해야 한다.

## Bundle ID (Android Application Id)

`BuildAndroid`는 게임마다 `com.gamefactory.<game_id>` 형태의 bundle id를 자동으로 만든다
(`Assets/GameFactory/Editor/BundleIdUtility.cs`). 한 번 만들어진 bundle id는
`GeneratedGames/<game_id>.json`(저장소 루트, Unity 에셋 아님)에 기록되고, 이후 재빌드에서는
그 값을 그대로 재사용한다 - **이미 배포된 게임의 bundle id가 재생성/재빌드로 바뀌는 일은 없다.**

`GameValidator`는 `GameSpecs/*.json` 전체에 대해 bundle id 충돌 여부를 미리 검사한다.

## 서명 (Signing)

Keystore 경로/비밀번호는 절대 저장소에 커밋하지 않는다. `BuildAndroid`는 다음 환경 변수를
읽어서 서명을 구성한다:

| 환경 변수 | 용도 |
|---|---|
| `ANDROID_KEYSTORE_PATH` | 이 self-hosted runner 위에 이미 존재하는 keystore 파일의 경로 |
| `ANDROID_KEYSTORE_PASS` | keystore 비밀번호 |
| `ANDROID_KEYALIAS_NAME` | key alias 이름 |
| `ANDROID_KEYALIAS_PASS` | key alias 비밀번호 |

`ANDROID_KEYSTORE_PATH`가 설정되어 있지 않으면 Unity의 기본 디버그 서명을 사용한다 - 기기에
설치해서 테스트하는 데는 문제가 없지만, Play Store에 제출할 수는 없다.

GitHub Actions에서 이 값들을 넘기려면 저장소 Settings → Secrets and variables → Actions에
`ANDROID_KEYSTORE_PATH`/`ANDROID_KEYSTORE_PASS`/`ANDROID_KEYALIAS_NAME`/`ANDROID_KEYALIAS_PASS`를
등록한다. **`ANDROID_KEYSTORE_PATH`는 파일 내용이 아니라, self-hosted runner 로컬 디스크에
이미 올려둔 keystore 파일의 경로 문자열이어야 한다** - keystore 파일 자체를 어떻게 그 runner에
배치할지(수동 복사, 별도 보안 채널 등)는 실제 서명 키를 발급받은 뒤 직접 결정해서 진행한다.

## 기타 Player Settings

`BuildAndroid.Build`가 빌드 직전에 다음을 설정한다:

- `PlayerSettings.productName` = GameSpec의 `game.title`
- `PlayerSettings.applicationIdentifier` = 위 bundle id
- `PlayerSettings.defaultInterfaceOrientation` = `Portrait`
- `PlayerSettings.bundleVersion` - 비어 있을 때만 `"1.0.0"`으로 초기화 (이미 값이 있으면 유지)
- `PlayerSettings.Android.bundleVersionCode` - `0` 이하일 때만 `1`로 초기화 (이미 값이 있으면 유지)

버전 코드/버전 문자열을 올리는 것은 이 자동화의 책임이 아니다 - 실제 배포 버전 관리 정책이
정해지면 그에 맞춰 별도로 갱신한다.
