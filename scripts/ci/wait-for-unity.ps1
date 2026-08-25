#Requires -Version 5.1
<#
.SYNOPSIS
  Launches Unity in batch mode and waits for it to ACTUALLY finish, then
  reports a real success/failure exit code.
.DESCRIPTION
  On this Windows self-hosted runner, launching Unity.exe directly via
  PowerShell's call operator and trusting its own process exit code is not
  reliable: Unity can relaunch itself as a separate process, so the process
  PowerShell was watching exits (near-instantly) long before the real work
  is done. That made every CI step "succeed" in ~5 seconds while Unity kept
  running detached in the background until the runner killed it as an
  orphan process at the end of the job - producing no scene/log/APK.

  This script waits until no process named "Unity" that started at/after
  THIS launch is still running (older Unity processes - e.g. someone's own
  interactive Editor session on the same machine - are ignored, since a
  system-wide "any Unity process" check would otherwise wait forever while
  an unrelated session stays open). It then determines the real outcome:
    - SentinelName: for -executeMethod entry points that write
      Logs/<name>.exitcode via CommandLineExit (GameFactoryGenerator,
      GameValidator, BuildAndroid). Missing sentinel = treated as failure.
    - TestResultsPath: for -runTests, which Unity controls internally and
      doesn't go through our sentinel. Checks the NUnit XML result file's
      root "result" attribute instead.
    - CompileLogPath: for a bare compile check (-quit with no
      -executeMethod). Scans the log for C# compiler errors. A sentinel is
      useless here by definition: when the code doesn't compile, there is
      no compiled assembly for -executeMethod to call into, so nothing
      could write one.
.PARAMETER UnityArgs
  Full argument list to pass to Unity.exe (batchmode/nographics/projectPath/etc).
.PARAMETER SentinelName
  Name (without extension) of the Logs/<name>.exitcode file to read.
.PARAMETER TestResultsPath
  Path to the -testResults XML file to check instead of a sentinel.
.PARAMETER CompileLogPath
  Path to the -logFile to scan for compiler errors instead of a sentinel.
.PARAMETER TimeoutMinutes
  Safety cap - if Unity is still running after this long, kill it and fail.
#>

param(
    [Parameter(Mandatory = $true)]
    [string[]]$UnityArgs,

    [string]$SentinelName,

    [string]$TestResultsPath,

    [string]$CompileLogPath,

    [int]$TimeoutMinutes = 30
)

$ErrorActionPreference = "Stop"

if (-not $SentinelName -and -not $TestResultsPath -and -not $CompileLogPath) {
    Write-Error "wait-for-unity.ps1: pass one of -SentinelName, -TestResultsPath, or -CompileLogPath."
    exit 1
}

New-Item -ItemType Directory -Path "Logs" -Force | Out-Null

if ($SentinelName) {
    $sentinelPath = Join-Path "Logs" "$SentinelName.exitcode"
    if (Test-Path $sentinelPath) { Remove-Item $sentinelPath -Force }
}

if ($TestResultsPath -and (Test-Path $TestResultsPath)) {
    Remove-Item $TestResultsPath -Force
}

$launchTime = (Get-Date).AddSeconds(-2)  # small buffer for clock/measurement skew
Write-Host "Launching: $env:UNITY_PATH $($UnityArgs -join ' ')"
Start-Process -FilePath $env:UNITY_PATH -ArgumentList $UnityArgs | Out-Null

$deadline = (Get-Date).AddMinutes($TimeoutMinutes)
$lastHeartbeat = Get-Date
while ($true) {
    Start-Sleep -Seconds 5
    $running = Get-Process -Name Unity -ErrorAction SilentlyContinue | Where-Object { $_.StartTime -ge $launchTime }
    if (-not $running) { break }

    if (((Get-Date) - $lastHeartbeat).TotalSeconds -ge 60) {
        $lastHeartbeat = Get-Date
        Write-Host "Still waiting on Unity (PID(s): $($running.Id -join ', '))..."
    }

    if ((Get-Date) -gt $deadline) {
        Write-Error "Timed out after $TimeoutMinutes minute(s) waiting for Unity to finish. Killing remaining Unity process(es)."
        $running | Stop-Process -Force
        exit 1
    }
}

Write-Host "No Unity process from this launch remains running."

if ($SentinelName) {
    if (-not (Test-Path $sentinelPath)) {
        Write-Error "Unity exited without writing $sentinelPath - it likely crashed or was killed before finishing. Check the -logFile output."
        exit 1
    }

    $code = (Get-Content $sentinelPath -Raw).Trim()
    Write-Host "Sentinel $sentinelPath reports exit code $code"
    exit ([int]$code)
}

if ($CompileLogPath) {
    if (-not (Test-Path $CompileLogPath)) {
        Write-Error "Unity exited without writing a log at $CompileLogPath - it likely failed to start at all."
        exit 1
    }

    # "error CS####" is what the C# compiler emits; the second pattern
    # catches the case where Unity reports the failure without echoing the
    # individual errors into this log.
    $compileErrors = Select-String -Path $CompileLogPath -Pattern 'error CS\d+', 'Scripts have compiler errors'
    if ($compileErrors) {
        Write-Host "Compile errors found in ${CompileLogPath}:"
        $compileErrors | ForEach-Object { Write-Host "  $($_.Line.Trim())" }
        exit 1
    }

    Write-Host "No compile errors found in $CompileLogPath."
    exit 0
}

if (-not (Test-Path $TestResultsPath)) {
    Write-Error "Unity exited without writing test results at $TestResultsPath - tests likely never completed. Check the -logFile output."
    exit 1
}

[xml]$results = Get-Content $TestResultsPath -Raw
$result = $results.'test-run'.result
$failed = $results.'test-run'.failed
Write-Host "Test results: result=$result failed=$failed"

if ($result -eq "Passed" -or $failed -eq "0") {
    exit 0
}

exit 1
