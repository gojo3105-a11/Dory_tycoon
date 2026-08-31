# AI_COMPANY_SETUP_REPORT

마스터 프롬프트 §40 구축 완료 체크리스트. **폴더만 만든 상태는 완료가 아니다**는 기준에 따라
실제로 실행해서 확인한 것만 PASS로 표시한다.

- 작성: 2026-08-31
- 대상 PC: `DESKTOP-A7IU1E9`, Windows 11 Pro
- 근거 파일: `config/HARDWARE_PROFILE.json`, `config/INSTALL_REPORT.json`,
  `config/cli-probes/*.txt`, `AI_GAME_COMPANY/tests/test_orchestrator.py`

## 실측된 하드웨어

| 항목 | 값 |
|---|---|
| CPU | 12th Gen Intel Core i5-1235U (10C/12T, 저전력 U 시리즈) |
| RAM | 15.7 GB 중 **5.9 GB 여유** |
| GPU | **Intel Iris Xe 내장** — 전용 GPU 없음, CUDA 없음 |
| Disk | 123 GB 여유 |
| Unity | `6000.5.9f1` — `ProjectVersion.txt`와 정확히 일치, Android SDK/JDK 동봉본 존재 |
| 유료 API 키 | 환경변수에 하나도 없음 |

**이 하드웨어가 계획을 바꾼다.** 아래 "현실적 자동화 수준" 참고.

## §40 체크리스트

| # | 항목 | 상태 | 근거 / 이유 |
|---|---|---|---|
| 1 | Hardware Profiler 작동 | **PASS** | 실제 PC에서 실행, `HARDWARE_PROFILE.json` 생성 확인 |
| 2 | Policy Loader 작동 | **PASS** | 단위 테스트 6개. 정책 파일이 없으면 **전부 거부**로 동작하는 것까지 검증 |
| 3 | State Manager 작동 | **PASS** | 테스트 6개. §15의 "COMPLETE인데 APK 없음 → 완료 취소" 시나리오 포함 |
| 4 | Task Queue 작동 | **PASS** | 테스트 7개. 증거 없이 PASS 불가, 우선순위, 재시도 escalate 검증 |
| 5 | Ollama localhost 호출 성공 | **LIMITED** | HTTP API 응답 확인(2154ms), 단 **설치된 모델 0개** |
| 6 | Local LLM 응답 저장 성공 | **NOT YET** | 모델을 아직 안 받았다. §4/§8에 따라 Model ID별 라이선스 확인 후 |
| 7 | Codex exec Test | **BLOCKED** | 설치는 됐으나 `--help` probe가 실행되지 않음(npm shim 문제, 수정 푸시함). 로그인은 HUMAN_GATE |
| 8 | Blender Background Test | **FAIL** | winget 설치는 성공(exit 0)했는데 PATH에 없음. Blender 설치기는 PATH를 안 건드린다 — 경로 탐색 추가해서 수정함, 재실행 필요 |
| 9 | Unity Batch Compile 성공 | **PASS** | CI에서 컴파일 에러 0개 확인 |
| 10 | Unity Android Build Test 성공 | **PASS** | 실제 APK 17.24 MB 생성 확인 (`sha256:60C6978B...`) |
| 11 | Build Log 수집 | **PASS** | `collect-errors.ps1` + `report-build-status.ps1`, 러너 워크스페이스까지 스캔 |
| 12 | Report Generator 작동 | **NOT YET** | `report_generator.py` 미작성 |
| 13 | Retry Manager 작동 | **PASS** | 테스트. §31의 "동일 Error Hash 반복 시 재시도 낭비 금지"까지 검증 |
| 14 | Resume Test 성공 | **PARTIAL** | 상태 재조정 로직은 단위 테스트 통과. 종단 resume은 아직 안 돌림 |
| 15 | License Registry 작동 | **PASS** | CC0 팩 4개를 동봉 라이선스 파일 근거로 APPROVED. **게이트를 코드로 강제** |
| 16 | Paid API 차단 Test 성공 | **PASS** | 테스트. 키가 있어도 정책이 false면 이름만 보고하고 값은 반환하지 않음 |

**요약: 16개 중 PASS 9, LIMITED/PARTIAL 2, NOT YET 2, BLOCKED 1, FAIL 1.**
핵심 인프라(정책/상태/큐/재시도/라이선스/Unity 빌드)는 동작한다. 막힌 것은 전부
**AI 도구 쪽**이고, 그 이유가 아래다.

## 현실적 자동화 수준 (§39) — 이 PC 기준

`doctor` 명령이 내리는 실제 판정:

| 능력 | 판정 | 이유 |
|---|---|---|
| Unity Android 빌드 | **VIABLE** | 이미 실제 APK를 만든 검증된 경로 |
| 로컬 LLM | **LIMITED** | `3b-q4` 등급까지. 여유 3.9 GB(5.9 − Unity용 2 GB). CPU 추론이라 느리다 — 짧은 JSON/설정 생성용이고 긴 추론용은 아니다 |
| 로컬 이미지 생성 | **NOT VIABLE** | 전용 GPU가 없다. Diffusion은 VRAM 6 GB급을 원하고, 내장 그래픽에서는 CPU로 떨어져 장당 수 분~수십 분 |
| Image-to-3D | **NOT VIABLE** | 같은 이유 + §10이 이미 "리깅된 게임 캐릭터 완성을 보장하지 않는다"고 명시 |
| Codex 코드리뷰 | **UNKNOWN** | probe 미실행 → 검증된 명령 목록 없음 → §41 STEP 5에 따라 어댑터 작성 금지 |

**이게 뜻하는 바를 숨기지 않고 적는다:** V2 마스터 프롬프트의 로컬 이미지 생성과
Image-to-3D는 이 PC에서 사실상 못 쓴다. 대신:

- **아트는 CC0 에셋 팩이 주력이다** (대체 수단이 아니라 1순위). §26도 라이선스 확인된
  기존 에셋을 AI 생성보다 상위에 둔다. 이미 4개 팩 APPROVED 완료
- **캐릭터는 Route B** — 라이선스 있는 pre-rigged 휴머노이드 + 도리의 외형
- **코드 리뷰는 Codex**(구독, 클라우드) — 로컬 모델로 대체할 영역이 아니다
- **ComfyUI는 이 PC에 설치하지 않는다** — 모델 가중치만 수십 GB 받고 못 돌린다

## 다음에 필요한 것

1. **PC에서 `detect-environment.ps1` 재실행** — npm shim / Blender·adb 경로 탐색 수정을 반영해야
   `claude`/`codex`/`blender`의 실제 `--help`가 잡힌다. 그게 없으면 §41 STEP 5 때문에
   어댑터를 못 쓴다
2. **Codex 로그인** (HUMAN_GATE) — `codex` 실행해서 ChatGPT 계정으로 로그인
3. 그 다음 `codex_runner.py` / `ollama_client.py` / `unity_runner.py` / `report_generator.py`

## 확인 방법

```powershell
cd C:\Dory_tycoon\AI_GAME_COMPANY
python -m company.orchestrator.main doctor
python -m company.orchestrator.main status
python ..\AI_GAME_COMPANY\tests\test_orchestrator.py
```

`doctor`는 `HARDWARE_PROFILE.json`이 없으면 "탐지기를 먼저 돌려라"라고 하고 종료한다 —
§38에 따라 설치되어 있다고 가정하지 않는다.
