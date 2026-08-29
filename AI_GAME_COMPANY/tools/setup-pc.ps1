#Requires -Version 5.1
<#
.SYNOPSIS
  One-shot PC bootstrap for the AI GAME COMPANY pipeline: install the missing
  free tools, survey what is actually on this machine, and push both reports
  so Claude Code can build adapters against reality.

.DESCRIPTION
  Runs, in order:
    1. install-missing-tools.ps1  (section 43 - free tools only)
    2. detect-environment.ps1     (sections 6 and 41 STEP 3-5)
    3. one commit + one push

  Step 2 runs even if step 1 partially failed, because a survey of a
  half-installed machine is still the information needed to decide what to do
  next - and hiding a failed install would violate section 38.

  This script does NOT git-merge before running. Pulling a newer version of
  this very script mid-execution would leave the old copy running, which is a
  confusing failure mode. Do the merge on the command line first; see README.

  ASCII only, deliberately: Windows PowerShell 5.1 reads a BOM-less UTF-8
  .ps1 using the local codepage, which mangles non-ASCII string literals.

.PARAMETER DryRun
  Pass through to the installer: report what would be installed, change
  nothing. The environment survey still runs, and nothing is committed.
#>

[CmdletBinding()]
param(
    [string]$RepoPath = "C:\Dory_tycoon",
    [string]$Branch = "claude/delete-current-content-mgn4xm",
    [string]$OriginRemote = "origin",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$toolsDir = Join-Path $RepoPath "AI_GAME_COMPANY\tools"
$installScript = Join-Path $toolsDir "install-missing-tools.ps1"
$detectScript = Join-Path $toolsDir "detect-environment.ps1"

foreach ($script in @($installScript, $detectScript)) {
    if (-not (Test-Path $script)) {
        throw "Missing $script - run 'git merge $OriginRemote/$Branch' first."
    }
}

function Write-Banner([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 70)
    Write-Host "  $Text"
    Write-Host ("=" * 70)
}

Write-Banner "STEP 1 / 3  Install missing free tools"

$installOk = $true
try {
    if ($DryRun) {
        & $installScript -RepoPath $RepoPath -Branch $Branch -OriginRemote $OriginRemote -DryRun
    }
    else {
        & $installScript -RepoPath $RepoPath -Branch $Branch -OriginRemote $OriginRemote -Commit -NoPush
    }
}
catch {
    $installOk = $false
    Write-Host "Installer stopped with an error: $($_.Exception.Message)"
    Write-Host "Continuing to the environment survey anyway - a survey of a"
    Write-Host "partially set up machine is still the information we need."
}

Write-Banner "STEP 2 / 3  Survey this machine"

if ($DryRun) {
    & $detectScript -RepoPath $RepoPath -Branch $Branch -OriginRemote $OriginRemote
}
else {
    & $detectScript -RepoPath $RepoPath -Branch $Branch -OriginRemote $OriginRemote -Commit -NoPush
}

Write-Banner "STEP 3 / 3  Push reports"

if ($DryRun) {
    Write-Host "DRY RUN - nothing committed, nothing pushed."
    Write-Host "Re-run without -DryRun to actually install and report."
    exit 0
}

$ErrorActionPreference = "Continue"
$attempt = 0
$pushed = $false

while ($attempt -lt 5 -and -not $pushed) {
    $output = & git -C $RepoPath push $OriginRemote $Branch 2>&1
    if ($LASTEXITCODE -eq 0) {
        $pushed = $true
        break
    }

    $attempt++
    if ($attempt -ge 5) {
        Write-Host "Push failed after 5 attempts:"
        Write-Host (($output | Out-String).Trim())
        break
    }

    $delay = [int][Math]::Pow(2, $attempt)
    Write-Host "Push failed; retrying in ${delay}s ..."
    Start-Sleep -Seconds $delay
}

Write-Host ""
if ($pushed) {
    Write-Host "Done. Reports pushed:"
    Write-Host "  AI_GAME_COMPANY/config/INSTALL_REPORT.json"
    Write-Host "  AI_GAME_COMPANY/config/HARDWARE_PROFILE.json"
    Write-Host "  AI_GAME_COMPANY/config/cli-probes/*.txt"
    Write-Host ""
    Write-Host "Claude Code can now build the orchestrator adapters against"
    Write-Host "what is actually installed here."
}
else {
    Write-Host "Reports were written and committed locally but NOT pushed."
    Write-Host "Run: git -C $RepoPath push $OriginRemote $Branch"
}

if (-not $installOk) {
    Write-Host ""
    Write-Host "NOTE: the installer did not finish cleanly - see the log under"
    Write-Host "AI_GAME_COMPANY/logs/ and INSTALL_REPORT.json for which tool failed."
}

exit 0
