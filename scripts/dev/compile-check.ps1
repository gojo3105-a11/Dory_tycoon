#Requires -Version 5.1
<#
.SYNOPSIS
  Compiles the project headlessly and reports whether there are any C#
  compile errors - without opening the Unity Editor and without running
  the whole generate/validate/test/build pipeline.

.DESCRIPTION
  Fast feedback loop for "does this even compile" after Claude Code pushes
  new scripts. Unity in batch mode imports assets and compiles all
  assemblies before quitting, so the errors land in the log; this scans
  for them and exits non-zero if any are found.

  Deliberately does NOT use an -executeMethod sentinel: broken code means
  there is no compiled assembly to call a method in, so a sentinel could
  never be written in exactly the case this script exists to detect.

.PARAMETER RepoPath
  The clone to compile. Defaults to C:\Dory_tycoon.

.NOTES
  Requires UNITY_PATH to point at Unity.exe (set once by
  scripts/windows-runner/03-set-unity-path-env.ps1).

  Close the Unity Editor first if it has this project open - Unity refuses
  to open the same project twice, and this will fail with a lock error
  rather than a compile result.
#>

[CmdletBinding()]
param(
    [string]$RepoPath = "C:\Dory_tycoon",
    [int]$TimeoutMinutes = 30
)

$ErrorActionPreference = "Stop"

if (-not $env:UNITY_PATH) {
    throw "UNITY_PATH is not set. Run scripts\windows-runner\03-set-unity-path-env.ps1 once, then open a new PowerShell window."
}

if (-not (Test-Path (Join-Path $RepoPath "Assets"))) {
    throw "'$RepoPath' does not look like the Unity project (no Assets folder). Pass -RepoPath <path>."
}

$waitScript = Join-Path (Split-Path $PSScriptRoot -Parent) "ci\wait-for-unity.ps1"
if (-not (Test-Path $waitScript)) {
    throw "Could not find wait-for-unity.ps1 at: $waitScript"
}

$logPath = Join-Path $RepoPath "Logs\unity-compile.log"
$logDir = Split-Path $logPath -Parent
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
if (Test-Path $logPath) { Remove-Item $logPath -Force }

Write-Host "Compiling $RepoPath (this takes a few minutes on a cold Library/)..."

# wait-for-unity.ps1 resolves Logs/ relative to the current directory.
Push-Location $RepoPath
try {
    & $waitScript -CompileLogPath $logPath -TimeoutMinutes $TimeoutMinutes -UnityArgs @(
        '-batchmode', '-nographics', '-projectPath', $RepoPath, '-quit',
        '-logFile', $logPath
    )
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($exitCode -eq 0) {
    Write-Host ""
    Write-Host "PASS - no compile errors." -ForegroundColor Green
}
else {
    Write-Host ""
    Write-Host "FAIL - see the errors above, full log: $logPath" -ForegroundColor Red
}

exit $exitCode
