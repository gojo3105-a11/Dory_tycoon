# 바탕화면에서 버튼 클릭으로 Game Factory 실행하기

명령어를 치지 않고, 바탕화면 아이콘을 더블클릭해서 GitHub Actions의 "Game Factory Pipeline"을
실행하는 방법이다.

## 최초 1회 설정

1. **GitHub CLI 설치** (PowerShell에서):
   ```
   winget install --id GitHub.cli
   ```
   설치 후 PowerShell 창을 새로 연다.

2. **로그인** (브라우저가 열리며 GitHub 계정으로 인증):
   ```
   gh auth login
   ```
   - "GitHub.com" 선택 → "HTTPS" 선택 → "Login with a web browser" 선택 → 코드 복사 후 브라우저에서 인증
   - `gojo3105` 계정으로 로그인한다 (fork 저장소 소유 계정).

3. **바탕화면 아이콘 만들기** (한 번만):
   ```
   cd C:\Dory_tycoon\scripts\desktop
   .\create-desktop-shortcut.ps1
   ```
   바탕화면에 **"Game Factory"** 아이콘이 생긴다.

## 사용법

1. 바탕화면의 **"Game Factory"** 아이콘 더블클릭
2. 실행할 GameSpec id를 묻는 입력창이 뜬다 (기본값 `game01`) → 확인
3. "실행을 요청했습니다" 창이 뜨면 완료 - GitHub Actions에서 self-hosted runner(이 PC의
   `run.cmd` 또는 서비스)가 이어받아 처리한다
4. "지금 진행 상황 페이지를 여시겠습니까?"에서 예를 누르면 브라우저로 Actions 페이지가 열린다

## 전제 조건

- `run-game-factory.ps1`에 적힌 저장소(`gojo3105/Dory_tycoon`)와 브랜치
  (`claude/delete-current-content-mgn4xm`)가 다르면 그 파일 위쪽의 `$RepoSlug`/`$Branch`
  변수를 실제 값으로 바꾼다.
- self-hosted runner(`run.cmd` 창 또는 서비스)가 실행 중이어야 실제로 작업이 처리된다 - 이
  아이콘은 "실행을 요청"만 할 뿐, runner가 꺼져 있으면 요청이 대기 상태로 남는다.
