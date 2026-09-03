#Requires -Version 5.1
<#
.SYNOPSIS
  One click: bring this clone up to date, start the control panel, open it.

  Replaces typing these by hand every time:
    cd C:\Dory_tycoon
    git pull upstream claude/delete-current-content-mgn4xm
    cd AI_GAME_COMPANY
    python -m company.orchestrator.main serve

.DESCRIPTION
  The panel must be started from AI_GAME_COMPANY because that is where the
  Python package lives - running it from the repository root fails with
  "No module named 'company'". This script handles the directory, the pull
  and the browser so none of that has to be remembered.

  The pull is done by sync-and-run.ps1 with -NoTrigger, so it follows the
  same rules as the scheduled sync (never merges over uncommitted edits to
  tracked files, never starts a pipeline run from here). If the sync refuses,
  the panel still opens on whatever is already checked out, and the reason
  is printed - a stale page is better than no page, but not silently.

  ASCII only, deliberately: Windows PowerShell 5.1 reads a BOM-less UTF-8
  .ps1 using the local codepage and mangles non-ASCII literals.

.PARAMETER NoPull
  Skip the sync and just start the panel.

.PARAMETER Port
  Port for the panel. Default 8765, the same as `orchestrator serve`.
#>

[CmdletBinding()]
param(
    [string]$RepoPath = "C:\Dory_tycoon",
    [string]$Branch = "claude/delete-current-content-mgn4xm",
    [int]$Port = 8765,
    [switch]$NoPull
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
    Write-Host "'$RepoPath' is not a git repository. Pass -RepoPath <path to the clone>."
    exit 2
}

if (-not $NoPull) {
    $sync = Join-Path $PSScriptRoot "sync-and-run.ps1"
    Write-Host "Syncing $Branch from upstream (no pipeline run)..."
    try {
        & $sync -RepoPath $RepoPath -Branch $Branch -NoTrigger -Silent
    }
    catch {
        Write-Host "Sync did not complete: $_"
        Write-Host "Opening the panel on the current checkout anyway."
    }
}

$companyRoot = Join-Path $RepoPath "AI_GAME_COMPANY"
if (-not (Test-Path (Join-Path $companyRoot "company\orchestrator\main.py"))) {
    Write-Host "AI_GAME_COMPANY\company\orchestrator\main.py not found under $RepoPath."
    exit 2
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "python is not on PATH."
    exit 2
}

# The server prints its own URL and starts serving before the browser asks,
# so a short delay is enough; the token lives inside the served page, which
# is why plain http://127.0.0.1:<port>/ is all the browser needs.
$url = "http://127.0.0.1:$Port/"
Start-Job -ScriptBlock {
    param($u)
    Start-Sleep -Seconds 2
    Start-Process $u
} -ArgumentList $url | Out-Null

Push-Location $companyRoot
try {
    & $python.Source -m company.orchestrator.main serve --port $Port
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
