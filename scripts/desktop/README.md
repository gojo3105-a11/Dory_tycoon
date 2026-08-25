# PC에서 Game Factory 자동 실행하기

Claude Code(원격 컨테이너)는 `gojo3105-a11/Dory_tycoon`(= `upstream`)에만 push할 수 있고,
self-hosted runner는 이 PC의 포크(`gojo3105/Dory_tycoon` = `origin`)에 등록되어 있다. 그래서
**upstream → 포크로 코드를 옮겨야 파이프라인이 돈다.** 예전에는 매번 이렇게 손으로 쳐야 했다:

```powershell
cd C:\Dory_tycoon
git fetch upstream
git merge upstream/claude/delete-current-content-mgn4xm
git push origin claude/delete-current-content-mgn4xm
```

이 폴더의 스크립트가 그 과정을 대신한다. 자동화 수준을 두 가지 중에 고르면 된다.

| 방식 | 필요한 조작 |
|---|---|
| **완전 자동** (권장) - `register-auto-sync.ps1` | 없음. 15분마다 알아서 확인/동기화/실행 |
| **원클릭** - 바탕화면 "Game Factory Sync & Run" 아이콘 | 아이콘 더블클릭 1번 |

## 최초 1회 설정

1. **GitHub CLI 설치** (PowerShell에서):
   ```powershell
   winget install --id GitHub.cli
   ```
   설치 후 PowerShell 창을 새로 연다.

2. **로그인** (브라우저가 열리며 GitHub 계정으로 인증):
   ```powershell
   gh auth login
   ```
   - "GitHub.com" → "HTTPS" → "Login with a web browser" → 코드 복사 후 브라우저에서 인증
   - **`gojo3105` 계정**으로 로그인한다 (포크 소유 계정).

3. **자동 동기화 등록** (완전 자동으로 쓸 경우):
   ```powershell
   cd C:\Dory_tycoon\scripts\desktop
   .\register-auto-sync.ps1
   ```
   15분마다 upstream을 확인해서 새 커밋이 있으면 포크로 옮기고 파이프라인을 실행한다.
   주기를 바꾸려면 `-IntervalMinutes 30`처럼 지정한다. 나중에 끄려면 `-Unregister`.

4. **바탕화면 아이콘 만들기** (원클릭으로도 쓰고 싶을 경우, 3번과 같이 써도 됨):
   ```powershell
   .\create-desktop-shortcut.ps1
   ```
   바탕화면에 아이콘 2개가 생긴다:
   - **"Game Factory Sync & Run"** - 동기화 + 파이프라인 실행 (평소 쓰는 것)
   - **"Game Factory Run Only"** - 동기화 없이 파이프라인만 재실행 (재시도용)

## Unity 에러를 Claude Code가 직접 읽게 하는 통로

Claude Code는 Unity가 없는 원격 컨테이너에서 돌기 때문에 PC의 컴파일 에러를 볼 수 없다. 그래서
`scripts/dev/collect-errors.ps1`이 Unity 로그에서 에러만 뽑아 `Reports/errors/latest.txt`로
커밋한다 - Claude Code는 저장소를 읽을 수 있으므로, 이제 복사/붙여넣기 없이 에러를 직접 확인한다.

`sync-and-run.ps1`이 매번 이걸 먼저 실행하므로 **자동 동기화를 켜뒀다면 따로 할 일이 없다.**
수동으로 지금 당장 올리고 싶으면:

```powershell
cd C:\Dory_tycoon
.\scripts\dev\collect-errors.ps1 -Commit
```

수집 대상:
- **Unity Editor.log** (`%LOCALAPPDATA%\Unity\Editor\Editor.log`) - Editor를 열어둔 상태에서도
  읽히고, **Play 모드에서 발생한 런타임 예외까지** 잡힌다.
- `<repo>\Logs\*.log` - 로컬에서 파이프라인이나 `compile-check.ps1`을 돌린 결과.

뽑아내는 항목: 컴파일 에러(`error CS####`), Obsolete API 경고(`CS0618`), 런타임 예외
(NullReferenceException 등). 내용이 이전과 같으면 커밋하지 않으므로 15분마다 같은 커밋이
쌓이지 않는다.

## 동작 방식

`sync-and-run.ps1`이 하는 일:

0. Unity 에러 리포트를 수집해서 (변경되었을 때만) 커밋한다 - 위 항목 참고.
1. 추적 중인 파일에 커밋 안 된 변경이 있으면 **아무것도 안 하고 중단한다** (작업물을 잃지 않도록).
   생성물처럼 추적되지 않는 파일은 무시한다.
2. `upstream`을 fetch하고 지정 브랜치를 merge한다. 충돌이 나면 `merge --abort`로 원래 상태로
   되돌리고 알려준다 (자동으로 충돌을 억지로 해결하지 않는다).
3. 포크(`origin`)로 push한다. 네트워크 실패는 2s/4s/8s/16s로 재시도한다.
4. 파이프라인을 정확히 한 번만 시작한다:
   - 받아온 커밋에 `GameSpecs/**` 변경이 있으면 → push 자체가 `game-factory.yml`을 자동
     트리거하므로 아무것도 더 하지 않는다.
   - C#/문서만 바뀌었으면 → `gh workflow run`으로 직접 실행한다 (push만으로는 안 돌기 때문).
   - 받아올 변경이 아예 없으면 → 실행하지 않는다 (의미 없는 CI 실행 방지).
   - `Reports/`(오류 리포트)만 바뀌었으면 → 실행하지 않는다. 리포트는 이 스크립트가 만든
     진단 파일일 뿐이므로, 그것 때문에 빌드가 돌면 안 된다.

로그는 `C:\Dory_tycoon\Logs\auto-sync.log`에 쌓인다 (git에 커밋되지 않는 폴더).

## 전제 조건 / 주의

- **self-hosted runner가 실행 중이어야 한다** (`run.cmd` 창). 스크립트는 "실행을 요청"만 하고,
  runner가 꺼져 있으면 요청은 큐에 대기 상태로 남는다.
- 자동 동기화 작업은 **로그인한 사용자 세션에서만** 돈다 (git 자격 증명과 runner가 그 사용자
  것이기 때문). 어차피 runner도 로그인 상태에서만 돌기 때문에 실질적인 제약은 아니다.
- 파이프라인이 도는 동안에는 Unity Editor를 열어두지 않는 게 안전하다 (같은 프로젝트를 두
  프로세스가 동시에 열면 충돌한다).
- 저장소/브랜치가 바뀌면 `sync-and-run.ps1` 위쪽 `param(...)`의 기본값(`$RepoPath`,
  `$Branch`, `$RepoSlug`)을 실제 값으로 바꾼다.
