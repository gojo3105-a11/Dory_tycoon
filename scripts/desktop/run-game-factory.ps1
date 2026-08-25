#Requires -Version 5.1
<#
.SYNOPSIS
  Double-click entry point (via the desktop shortcut created by
  create-desktop-shortcut.ps1) that asks for a GameSpec id with a small
  popup and triggers the "Game Factory Pipeline" GitHub Actions workflow
  for it - no terminal, no typed commands.
.NOTES
  Requires the GitHub CLI (`gh`) installed and logged in once beforehand:
    winget install --id GitHub.cli
    gh auth login
  Unverified against a real Windows machine.
#>

$ErrorActionPreference = "Stop"

$RepoSlug = "gojo3105/Dory_tycoon"
$Branch = "claude/delete-current-content-mgn4xm"
$Workflow = "game-factory.yml"

Add-Type -AssemblyName Microsoft.VisualBasic
Add-Type -AssemblyName System.Windows.Forms

function Show-Info($message, $title) {
    [System.Windows.Forms.MessageBox]::Show($message, $title, "OK", "Information") | Out-Null
}

function Show-ErrorBox($message) {
    [System.Windows.Forms.MessageBox]::Show($message, "Game Factory", "OK", "Error") | Out-Null
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Show-ErrorBox "GitHub CLI(gh)가 설치되어 있지 않습니다.`n`nPowerShell에서 아래 명령으로 설치 후 'gh auth login'으로 로그인해주세요:`n`nwinget install --id GitHub.cli"
    exit 1
}

$gameId = [Microsoft.VisualBasic.Interaction]::InputBox(
    "실행할 GameSpec id를 입력하세요 (GameSpecs/<id>.json)",
    "Game Factory 실행",
    "game01"
)

if ([string]::IsNullOrWhiteSpace($gameId)) {
    exit 0
}

try {
    & gh workflow run $Workflow --repo $RepoSlug --ref $Branch -f "game_id=$gameId" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "gh workflow run exited with code $LASTEXITCODE"
    }
}
catch {
    Show-ErrorBox "실행 요청에 실패했습니다:`n`n$_`n`n'gh auth login'으로 로그인되어 있는지 확인해주세요."
    exit 1
}

$openLog = [System.Windows.Forms.MessageBox]::Show(
    "'$gameId' 파이프라인 실행을 요청했습니다.`n`n지금 GitHub Actions 진행 상황 페이지를 여시겠습니까?",
    "Game Factory",
    "YesNo",
    "Information"
)

if ($openLog -eq "Yes") {
    Start-Process "https://github.com/$RepoSlug/actions"
}
