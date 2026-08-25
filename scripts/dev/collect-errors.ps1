#Requires -Version 5.1
<#
.SYNOPSIS
  Extracts compile errors and runtime exceptions out of Unity's logs into a
  small committed text file, so Claude Code (which runs in a container with
  no Unity and no access to this PC) can read them straight from the repo
  instead of asking for a copy-paste every time.

.DESCRIPTION
  Reads whichever of these exist and are recent:
    - Unity Editor.log (%LOCALAPPDATA%\Unity\Editor\Editor.log) - this is
      the live Editor's own log, so it works while the Editor is open and
      captures Play-mode exceptions too.
    - <repo>\Logs\*.log - local pipeline/compile-check runs.

  Writes Reports/errors/latest.txt. Returns exit code 0 whether or not
  errors were found - "no errors" is a perfectly good report, and the
  caller decides what to do about it.

.PARAMETER Commit
  Also commit the report when its content changed, and push it to the fork.
  This is what makes it visible to Claude Code.

.PARAMETER NoPush
  With -Commit, commit locally but leave the push to the caller. Used by
  sync-and-run.ps1, which pushes once at the end of its own flow.

.NOTES
  The Editor holds Editor.log open, so it is read with an explicit
  read/write share mode rather than plain Get-Content.
#>

[CmdletBinding()]
param(
    [string]$RepoPath = "C:\Dory_tycoon",
    [string]$Branch = "claude/delete-current-content-mgn4xm",
    [string]$OriginRemote = "origin",
    [int]$TailLines = 8000,
    [int]$MaxPerSection = 60,
    [switch]$Commit,
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"

$reportRelativePath = "Reports/errors/latest.txt"
$reportPath = Join-Path $RepoPath ($reportRelativePath -replace '/', '\')

# Reads a file that another process may hold open for writing (Editor.log).
function Read-SharedFile([string]$path, [int]$tail) {
    $stream = $null
    $reader = $null
    try {
        $stream = [System.IO.File]::Open($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        $reader = New-Object System.IO.StreamReader($stream)
        $lines = $reader.ReadToEnd() -split "\r?\n"
    }
    finally {
        if ($reader) { $reader.Dispose() }
        if ($stream) { $stream.Dispose() }
    }

    if ($lines.Count -gt $tail) { return $lines[-$tail..-1] }
    return $lines
}

function Invoke-Git {
    param([Parameter(Mandatory = $true)][string[]]$Arguments, [int]$Retries = 0)

    $ErrorActionPreference = "Continue"
    $attempt = 0

    while ($true) {
        $output = & git -C $RepoPath @Arguments 2>&1
        if ($LASTEXITCODE -eq 0) { return ($output | Out-String).Trim() }

        if ($attempt -ge $Retries) {
            throw "git $($Arguments -join ' ') failed (exit $LASTEXITCODE):`n$(($output | Out-String).Trim())"
        }

        Start-Sleep -Seconds ([Math]::Pow(2, $attempt + 1))
        $attempt++
    }
}

$sources = @()

$editorLog = Join-Path $env:LOCALAPPDATA "Unity\Editor\Editor.log"
if (Test-Path $editorLog) { $sources += $editorLog }

$repoLogDir = Join-Path $RepoPath "Logs"
if (Test-Path $repoLogDir) {
    $sources += (Get-ChildItem -Path $repoLogDir -Filter *.log -File | Sort-Object LastWriteTime -Descending | Select-Object -ExpandProperty FullName)
}

if (-not $sources) {
    throw "No Unity logs found. Looked for '$editorLog' and '$repoLogDir\*.log'."
}

$compileErrors = New-Object System.Collections.Generic.List[string]
$obsoleteWarnings = New-Object System.Collections.Generic.List[string]
$exceptions = New-Object System.Collections.Generic.List[string]
$scanned = New-Object System.Collections.Generic.List[string]

foreach ($source in $sources) {
    $lines = Read-SharedFile $source $TailLines
    $scanned.Add(("{0}  (수정: {1}, 스캔한 줄: {2})" -f $source, (Get-Item $source).LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss"), $lines.Count))

    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if (-not $trimmed) { continue }

        if ($trimmed -match 'error CS\d+' -or $trimmed -match 'Scripts have compiler errors') {
            if (-not $compileErrors.Contains($trimmed)) { $compileErrors.Add($trimmed) }
        }
        elseif ($trimmed -match 'warning CS0618') {
            # Obsolete-API warnings are the ones worth acting on; other
            # warnings are noise for this purpose.
            if (-not $obsoleteWarnings.Contains($trimmed)) { $obsoleteWarnings.Add($trimmed) }
        }
        elseif ($trimmed -match '^\w*(Exception|Error):' -or $trimmed -match 'NullReferenceException|MissingReferenceException|MissingComponentException|UnassignedReferenceException') {
            if (-not $exceptions.Contains($trimmed)) { $exceptions.Add($trimmed) }
        }
    }
}

function Format-Section([string]$title, $items) {
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("## $title ($($items.Count))")
    [void]$sb.AppendLine()

    if ($items.Count -eq 0) {
        [void]$sb.AppendLine("없음.")
    }
    else {
        $shown = if ($items.Count -gt $MaxPerSection) { $items[0..($MaxPerSection - 1)] } else { $items }
        foreach ($item in $shown) { [void]$sb.AppendLine("- $item") }
        if ($items.Count -gt $MaxPerSection) {
            [void]$sb.AppendLine("- ... ($($items.Count - $MaxPerSection)개 더 있음, 전체는 원본 로그 참고)")
        }
    }

    [void]$sb.AppendLine()
    return $sb.ToString()
}

$report = New-Object System.Text.StringBuilder
[void]$report.AppendLine("# Unity 오류 리포트")
[void]$report.AppendLine()
[void]$report.AppendLine("이 파일은 scripts/dev/collect-errors.ps1이 자동 생성한다. 손으로 편집하지 않는다.")
[void]$report.AppendLine("Unity가 없는 원격 컨테이너에서 Claude Code가 PC의 컴파일 에러를 직접 읽기 위한 통로다.")
[void]$report.AppendLine()
[void]$report.AppendLine("생성 시각: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
[void]$report.AppendLine()
[void]$report.AppendLine("## 스캔한 로그")
[void]$report.AppendLine()
foreach ($entry in $scanned) { [void]$report.AppendLine("- $entry") }
[void]$report.AppendLine()
[void]$report.Append((Format-Section "컴파일 에러" $compileErrors))
[void]$report.Append((Format-Section "Obsolete API 경고 (CS0618)" $obsoleteWarnings))
[void]$report.Append((Format-Section "런타임 예외" $exceptions))

$reportDir = Split-Path $reportPath -Parent
if (-not (Test-Path $reportDir)) { New-Item -ItemType Directory -Path $reportDir -Force | Out-Null }
Set-Content -Path $reportPath -Value $report.ToString() -Encoding UTF8

Write-Host "컴파일 에러 $($compileErrors.Count)개, CS0618 경고 $($obsoleteWarnings.Count)개, 런타임 예외 $($exceptions.Count)개"
Write-Host "리포트: $reportPath"

if (-not $Commit) {
    Write-Host "(-Commit 을 주면 저장소에 커밋/푸시해서 Claude Code가 읽을 수 있게 합니다.)"
    exit 0
}

# Only commit when the findings actually changed - otherwise a scheduled
# run every 15 minutes would spam the history with identical commits.
# --ignore-matching-lines skips the timestamp/scan-metadata lines, which
# differ on every single run by design.
$ErrorActionPreference = "Continue"
& git -C $RepoPath diff --quiet --ignore-matching-lines='^(생성 시각|- .*스캔한 줄)' -- $reportRelativePath 2>&1 | Out-Null
$unchangedTracked = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"

$isTracked = $true
try { Invoke-Git @("ls-files", "--error-unmatch", $reportRelativePath) | Out-Null }
catch { $isTracked = $false }

if ($isTracked -and $unchangedTracked) {
    Write-Host "이전 리포트와 내용이 같아서 커밋하지 않았습니다."
    exit 0
}

Invoke-Git @("add", $reportRelativePath) | Out-Null
Invoke-Git @("commit", "-m", "chore: update Unity error report ($($compileErrors.Count) compile error(s))") | Out-Null

if ($NoPush) {
    Write-Host "리포트를 커밋했습니다 (push는 호출한 쪽에서 처리)."
    exit 0
}

Invoke-Git @("push", $OriginRemote, $Branch) -Retries 4 | Out-Null
Write-Host "리포트를 포크에 push했습니다. Claude Code가 이제 읽을 수 있습니다."
exit 0
