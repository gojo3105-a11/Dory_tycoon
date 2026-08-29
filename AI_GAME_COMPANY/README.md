# AI_GAME_COMPANY

`AI GAME COMPANY - EXECUTABLE MASTER PROMPT V2`를 실행하기 위한 오케스트레이션 계층이다.
기존 Unity 프로젝트를 **대체하지 않고 그 위에 얹힌다.**

## 왜 Unity 프로젝트를 여기로 옮기지 않았나 (구조 결정)

마스터 프롬프트 §12의 폴더 구조에는 `AI_GAME_COMPANY/games/Game01..Game10`과 `builds/`가 있다.
그대로 따르면 저장소 루트의 기존 `Assets/`, `GameSpecs/`, `Builds/`와 충돌하거나 이동이 필요하다.

그런데 §19는 이렇게 말한다: *"현재 정상 확인된 TEST APK 프로젝트가 있다면 그 프로젝트의 Android
설정을 Baseline으로 삼는다... 정상 설정을 이유 없이 변경하지 않는다."* §38은 *"정상 TEST APK
설정을 Backup 없이 변경"*을 금지한다.

우리는 **실제로 동작하는 검증된 빌드가 있다**(아래 Baseline 참고). Unity 프로젝트를 하위 폴더로
옮기면 `ProjectSettings`, Gradle 경로, `.github/workflows`의 `-projectPath`, self-hosted runner의
체크아웃 경로, `report-build-status.ps1`의 스캔 경로가 전부 깨진다. 그 위험을 감수할 이유가 없다.

**따라서:**

| 무엇 | 어디에 | 이유 |
|---|---|---|
| Unity 프로젝트 (`Assets/`, `ProjectSettings/`, `Packages/`) | 저장소 루트 (그대로) | §19 Baseline 보존 |
| APK 산출물 (`Builds/<gameId>/`) | 저장소 루트 (그대로) | CI·리포트 스크립트가 이미 여기를 본다 |
| 게임별 Unity 코드 | `Assets/GameFactory/`, `Assets/Games/` | Unity가 요구하는 위치 |
| 오케스트레이터, 정책, 라이선스, AI 도구 어댑터, 상태/큐 | **`AI_GAME_COMPANY/`** | 신규 |
| 게임별 오케스트레이션 산출물(계획, AI 활동 로그, 상태) | `AI_GAME_COMPANY/games/GameXX/` | Unity 에셋 아님 |

즉 `AI_GAME_COMPANY/games/`는 **Unity 에셋이 아니라 생산 관리 데이터**를 담는다.

## Baseline (§19)

검증된 APK를 만들어낸 상태:

- 커밋: `adcce3c` (빌드 관련 트리는 `6a8de00`과 동일 — `adcce3c`는 문서만 추가)
- 산출물: `Game01_FactoryRunner_v1.0.apk`, 17.24 MB, `sha256:60C6978B1E8C2889`
- 빌드 시각: 2026-08-27 20:50:47, self-hosted runner, 컴파일 에러 0

`ProjectSettings`, `Packages`, Gradle 설정, Android SDK/JDK 경로, Player Settings를 이 시점에서
**이유와 백업 없이 변경하지 않는다.**

> 참고: 이 상태를 git 태그로도 남기려 했으나 원격이 태그 push를 거부했다(403 — 이 환경은 지정
> 브랜치 push만 허용). 그래서 Baseline을 이 파일에 기록한다. PC에서 태그를 남기고 싶으면:
> `git tag -a baseline/verified-apk-v1 adcce3c -m "verified APK baseline" && git push origin baseline/verified-apk-v1`

## 지금 상태

| STEP (§41) | 내용 | 상태 |
|---|---|---|
| 1 | 저장소/Unity 프로젝트 분석 | 완료 (`PROJECT_ANALYSIS.md`, `Documentation/CURRENT_GAME_ANALYSIS.md`) |
| 2 | 안전한 Git Baseline | 완료 (위 Baseline 절) |
| 3-5 | 하드웨어 프로파일 + 프로그램 탐지 + CLI `--help` 검증 | **도구 작성 완료, PC 실행 대기** |
| 6 | `company_policy.json` | 완료 |
| 7 | `LICENSE_REGISTRY.json` | 완료 (초기 등록) |
| 8 | 폴더 구조 | 진행 중 (내용이 생기는 대로 생성) |
| 9-16 | Orchestrator / Adapter / Runner | **STEP 3-5 결과 대기** |

## 왜 STEP 3-5가 모든 것을 막고 있나

Claude Code는 리눅스 원격 컨테이너에서 돈다. **Unity도, GPU도, Ollama도, Codex도, Blender도
여기 없다.** 여기서 `ollama list`를 실행하면 "없음"이 나오지만 그건 사용자 PC의 사실이 아니다.

그리고 §41 STEP 5는 *"각 CLI의 실제 --help를 읽고 지원되는 명령만 Adapter에 반영"*하라고 하고,
§38은 *"존재하지 않는 CLI 명령 추측"*을 금지한다. 즉 **실제 PC 데이터 없이 어댑터를 쓰는 것은
규칙 위반이다.** 추측으로 `codex exec --json --schema ...`를 짜 놓으면 그 플래그가 실제로 존재하는지
알 수 없다.

그래서 먼저 PC에서 이걸 실행해야 한다. **한 번에 다 하는 방법:**

```powershell
cd C:\Dory_tycoon
git fetch origin claude/delete-current-content-mgn4xm
git merge origin/claude/delete-current-content-mgn4xm

# 먼저 뭘 설치할지만 보고 싶으면 (아무것도 안 바꿈)
.\AI_GAME_COMPANY\tools\setup-pc.ps1 -DryRun

# 실제 실행: 없는 무료 도구 설치 -> 환경 조사 -> 커밋/푸시
.\AI_GAME_COMPANY\tools\setup-pc.ps1
```

`git merge`를 스크립트 안에서 하지 않는 이유: 실행 도중에 이 스크립트 자신의 새 버전을 받아버리면
구버전이 계속 돌아가는 헷갈리는 상황이 된다. 병합은 명령줄에서 먼저 한다.

산출물:

- `AI_GAME_COMPANY/config/HARDWARE_PROFILE.json` — CPU/RAM/GPU/VRAM, 각 도구의 installed/version/path/status,
  Ollama HTTP API 상태와 설치 모델 목록, Unity 버전 매칭, Android SDK/JDK 경로
- `AI_GAME_COMPANY/config/INSTALL_REPORT.json` — 무엇을 설치했고 무엇을 왜 안 했는지
- `AI_GAME_COMPANY/config/cli-probes/*.txt` — 각 CLI의 **원본 `--help` 텍스트**

이 세 가지가 올라오면 그때부터 실제 지원되는 명령만으로 어댑터를 쓴다.

### 자동 설치 정책 (§43)

§43은 *"추가 유료 비용 없이 설치 가능한 구성요소라면 설치 계획을 만들고 가능한 범위에서 진행한다"*고
허용한다. 그래서 **무료·로그인 불필요**한 것만 자동 설치한다.

| 대상 | 자동 설치 | 방법 | 비고 |
|---|---|---|---|
| Git | O | winget | |
| Python 3 | O | winget | Orchestrator가 Python(§13) |
| Node.js LTS | O | winget | Codex/Claude CLI 설치에 필요 |
| Ollama **서버** | O | winget | 서버만. 모델은 아래 참고 |
| Blender | O | winget | §11 background 스크립트용 |
| Codex CLI | O (설치만) | npm | **로그인은 HUMAN_GATE**(§37) |
| Claude Code CLI | O (설치만) | npm | **로그인은 HUMAN_GATE**(§37) |
| **Unity** | **X** | — | 라이선스 + §19 검증된 Baseline. 자동 설치/업그레이드가 유일하게 동작하는 파이프라인을 깨뜨릴 수 있다 |
| **Ollama 모델** | **X** | — | §4/§8. Model ID별 라이선스 확인 후 `LICENSE_REGISTRY.json`에 APPROVED가 되어야 받는다. "Qwen이니까 괜찮다"는 명시적으로 불충분 |
| **ComfyUI / 이미지·3D 모델** | **X** | — | §9. 설치 전 저장소 라이선스 확인 필수 |
| 유료 소프트웨어 | **X** | — | `PAID_ACTION_BLOCKED`로 기록, 결제 안 함 |

설치기는 **패키지 ID를 추측해서 바로 실행하지 않는다.** §38("존재하지 않는 CLI 명령 추측 금지")에
따라 먼저 `winget search --exact`로 해당 ID가 실제로 존재하는지 확인하고, 없으면
`PACKAGE_ID_NOT_FOUND`로 기록한 뒤 넘어간다.

winget의 표준 source/package 동의(`--accept-source-agreements`, `--accept-package-agreements`)는
자동으로 처리되며, 어떤 동의를 자동 수락했는지 `INSTALL_REPORT.json`의 `autoAcceptedAgreements`에
그대로 남긴다. winget 자체가 없으면 `BLOCKED_NO_PACKAGE_MANAGER`로 기록한다(Microsoft Store의
"App Installer" 설치 필요).

각 항목은 §43 형식대로 EXPECTED / ACTUAL / STATUS / LOG_PATH / OUTPUT_PATH로 기록된다.
상태값: `ALREADY_INSTALLED`, `INSTALLED`, `WOULD_INSTALL`(DryRun), `FAILED`, `SKIPPED_POLICY`,
`HUMAN_GATE`, `LICENSE_CHECK_REQUIRED`, `PACKAGE_ID_NOT_FOUND`, `BLOCKED_NO_PACKAGE_MANAGER`,
`BLOCKED_MISSING_DEPENDENCY`.

### 보안 (§3, §7)

탐지 스크립트는:

- API 키/토큰의 **값을 절대 기록하지 않는다.** 존재 여부(`true`/`false`)만 남긴다 — §7이
  "키가 있어도 정책이 false면 사용 금지"를 판정하려면 존재 여부를 알아야 하기 때문이다.
- `~/.codex/auth.json` 같은 인증 파일을 읽거나 복사하지 않는다.
- 로그인 상태는 각 CLI 자신의 상태 명령으로만 확인한다.

## 알려진 미해결 사항

- **캐릭터 레퍼런스 이미지 15장의 라이선스가 UNKNOWN이다**(`LICENSE_REGISTRY.json` 참고).
  현재는 소스로만 존재하고 APK에 들어가지 않으므로 당장 문제는 없다. 다만 여기서 파생된 3D 모델이나
  텍스처를 출시 빌드에 넣기 전에는 출처 확인이 필요하다(§8, §38).
- Codex / Ollama / Blender / ComfyUI 설치 여부 자체가 아직 확인되지 않았다.
