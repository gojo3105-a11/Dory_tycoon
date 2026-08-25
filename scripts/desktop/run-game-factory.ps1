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
    Show-ErrorBox "The GitHub CLI (gh) is not installed.`n`nInstall it from PowerShell and then run 'gh auth login':`n`nwinget install --id GitHub.cli"
    exit 1
}

$gameId = [Microsoft.VisualBasic.Interaction]::InputBox(
    "Which GameSpec id should run? (GameSpecs/<id>.json)",
    "Run Game Factory",
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
    Show-ErrorBox "The run request failed:`n`n$_`n`nCheck that you are logged in with 'gh auth login'."
    exit 1
}

$openLog = [System.Windows.Forms.MessageBox]::Show(
    "Requested a pipeline run for '$gameId'.`n`nOpen the GitHub Actions progress page now?",
    "Game Factory",
    "YesNo",
    "Information"
)

if ($openLog -eq "Yes") {
    Start-Process "https://github.com/$RepoSlug/actions"
}
