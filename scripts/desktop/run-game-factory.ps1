#Requires -Version 5.1
<#
.SYNOPSIS
  Double-click entry point (via the desktop shortcut created by
  create-desktop-shortcut.ps1) that asks for a GameSpec id with a small
  popup and triggers the "Game Factory Pipeline" GitHub Actions workflow
  for it - no terminal, no typed commands.
.DESCRIPTION
  Prefers `gh workflow run` (works for any game id) when the GitHub CLI is
  installed and logged in. When it is not, falls back to committing a
  bump to GameSpecs/.ci-trigger and pushing it, which reaches the same
  `on: push: paths: GameSpecs/**` trigger game-factory.yml already reacts
  to - no CLI, no token needed. That push-triggered path always runs with
  the workflow's default game_id ('game01'), so without gh this can only
  ever target game01; asking for anything else without gh installed is
  refused rather than silently building the wrong game.
.NOTES
  The GitHub CLI (`gh`) is optional - see .DESCRIPTION. If you want it:
    winget install --id GitHub.cli
    gh auth login
#>

param(
    [string]$RepoPath = "C:\Dory_tycoon",
    [string]$OriginRemote = "origin"
)

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

function Ask-YesNo($message, $title) {
    $result = [System.Windows.Forms.MessageBox]::Show($message, $title, "YesNo", "Question")
    return $result -eq "Yes"
}

function Invoke-Git {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $ErrorActionPreference = "Continue"
    $output = & git -C $RepoPath @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"

    if ($exitCode -ne 0) {
        throw "git $($Arguments -join ' ') failed (exit $exitCode):`n$(($output | Out-String).Trim())"
    }

    return ($output | Out-String).Trim()
}

$gameId = [Microsoft.VisualBasic.Interaction]::InputBox(
    "Which GameSpec id should run? (GameSpecs/<id>.json)",
    "Run Game Factory",
    "game01"
)

if ([string]::IsNullOrWhiteSpace($gameId)) {
    exit 0
}

$hasGh = [bool](Get-Command gh -ErrorAction SilentlyContinue)

if (-not $hasGh -and $gameId -ne "game01") {
    $useGame01Instead = Ask-YesNo (
        "The GitHub CLI (gh) is not installed, so '$gameId' cannot be targeted directly - " +
        "the fallback trigger can only start 'game01'.`n`n" +
        "Run 'game01' instead? (Or install gh for arbitrary game ids: winget install --id GitHub.cli)"
    ) "Game Factory"

    if (-not $useGame01Instead) { exit 0 }
    $gameId = "game01"
}

if ($hasGh) {
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
}
else {
    try {
        if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
            throw "'$RepoPath' is not a git repository."
        }

        $triggerPath = Join-Path $RepoPath "GameSpecs\.ci-trigger"
        $triggerContent = "Bumped $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') to start the Game Factory Pipeline for '$gameId' without the GitHub CLI. Not a GameSpec - GameValidator only reads *.json here."
        Set-Content -Path $triggerPath -Value $triggerContent -Encoding UTF8

        Invoke-Git @("add", "GameSpecs/.ci-trigger") | Out-Null
        Invoke-Git @("commit", "-m", "chore: trigger Game Factory Pipeline for $gameId") | Out-Null
        Invoke-Git @("push", $OriginRemote, $Branch) | Out-Null
    }
    catch {
        Show-ErrorBox "The trigger-file push failed:`n`n$_"
        exit 1
    }
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
