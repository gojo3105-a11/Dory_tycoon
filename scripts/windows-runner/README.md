# Windows Self-hosted Runner 설정 스크립트

이 폴더의 PowerShell 스크립트들은 `docs/AUTOMATION.md`에서 설명하는 self-hosted runner를
실제 Windows PC에 준비하는 작업을 자동화한다. **모두 그 Windows PC에서, 관리자 권한
PowerShell로 실행한다** (이 저장소를 다루는 Claude Code 원격 컨테이너가 아니다 - 이 컨테이너는
조직 네트워크 정책상 Unity 다운로드 서버에 접근할 수 없다).

이 스크립트들은 실제 Windows 환경에서 검증된 적이 없다 (작성 시점에 Windows 머신에 접근할
수 없었음). 실행 전에 내용을 한 번 읽어보고, 문제가 생기면 각 단계를 수동으로 대체할 수 있게
스크립트를 짧고 단순하게 유지했다.

## 실행 순서

```powershell
# 1. Unity Hub 설치 (이미 설치되어 있다면 건너뛴다)
.\01-install-unity-hub.ps1

# 2. Unity Hub를 한 번 실행해서 Unity ID로 로그인하고 라이선스를 활성화한다 (수동, GUI)
#    Personal license면: Unity Hub > 오른쪽 위 계정 아이콘 > Manage Licenses > Add > Personal
#    이 머신에서 한 번만 하면 되고, 이후에는 배치 모드 빌드에 별도 로그인이 필요 없다.

# 3. Unity Editor 설치 (ProjectSettings/ProjectVersion.txt에 적힌 버전 + Android Build Support)
.\02-install-unity-editor.ps1 -Version 6000.0.36f1

# 4. UNITY_PATH 환경 변수를 자동으로 찾아서 설정
.\03-set-unity-path-env.ps1

# 5. GitHub Actions self-hosted runner 등록
#    토큰은 GitHub 저장소 Settings > Actions > Runners > New self-hosted runner 에서 발급받는다
#    (1시간 후 만료되므로 발급 직후에 바로 실행한다)
.\04-register-github-runner.ps1 -RepoUrl "https://github.com/gojo3105-a11/Dory_tycoon" -Token "<발급받은 토큰>"
```

각 단계 후 새 PowerShell 창을 열어야 방금 설정한 환경 변수가 반영된다 (특히 3, 4단계 사이).

## 확인

```powershell
# UNITY_PATH가 올바른지 확인
& "$env:UNITY_PATH" -version

# runner가 서비스로 떠 있는지 확인
Get-Service actions.runner.*
```

이후 GitHub 저장소의 Settings > Actions > Runners에 이 머신이 "Idle" 상태로 보이면 준비 완료다.
`.github/workflows/validate.yml` 등을 `workflow_dispatch`로 수동 실행해서 끝까지 통과하는지
확인해보는 것을 권장한다.
