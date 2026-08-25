#Requires -Version 5.1
<#
.SYNOPSIS
  One-time setup for hands-off operation: registers a Windows Scheduled
  Task that runs sync-and-run.ps1 every N minutes, so work pushed to the
  upstream repo lands on this fork - and starts a pipeline run - without
  anyone typing or clicking anything.

.DESCRIPTION
  The task runs as the current interactive user (not SYSTEM/NetworkService)
  because git needs that user's stored credentials to push, and because
  the self-hosted runner is itself run interactively by that user. It
  therefore only fires while that user is logged in, which is exactly when
  the runner is available to pick the job up anyway.

  Uses -Silent, so a run that finds nothing to do is completely quiet;
  everything lands in Logs/auto-sync.log.

.PARAMETER IntervalMinutes
  How often to check upstream. Default 15.

.PARAMETER Unregister
  Remove the task instead of creating it.

.NOTES
  Run once from a normal (non-elevated is fine) PowerShell window:
    .\scripts\desktop\register-auto-sync.ps1
  Check state any time with:
    Get-ScheduledTask -TaskName "Game Factory Auto Sync"
    Get-ScheduledTaskInfo -TaskName "Game Factory Auto Sync"
#>

[CmdletBinding()]
param(
    [int]$IntervalMinutes = 15,
    [string]$RepoPath = "C:\Dory_tycoon",
    [string]$TaskName = "Game Factory Auto Sync",
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task: $TaskName"
    exit 0
}

$syncScript = Join-Path $PSScriptRoot "sync-and-run.ps1"
if (-not (Test-Path $syncScript)) {
    throw "Could not find sync-and-run.ps1 next to this script at: $syncScript"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (
    "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$syncScript`" -RepoPath `"$RepoPath`" -Silent"
)

# Starts a few minutes from now so registering this doesn't immediately
# collide with whatever the user is doing right now. RepetitionDuration is
# set explicitly (rather than relying on a version-dependent default for
# "indefinitely") to a span long enough to outlive this project.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Syncs the Dory_tycoon fork from upstream every $IntervalMinutes minutes and starts the Game Factory Pipeline when there is new work." `
    -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' (every $IntervalMinutes minutes, as $env:USERNAME)."
Write-Host "Log: $(Join-Path $RepoPath 'Logs\auto-sync.log')"
Write-Host "Remove it later with: .\register-auto-sync.ps1 -Unregister"
