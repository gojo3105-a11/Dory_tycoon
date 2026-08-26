#Requires -Version 5.1
<#
.SYNOPSIS
  Extracts compile errors and runtime exceptions out of Unity's logs into a
  small committed text file, so Claude Code (which runs in a container with
  no Unity and no access to this PC) can read them straight from the repo
  instead of asking for a copy-paste every time.

.DESCRIPTION
  Reads whichever of these exist:
    - Unity Editor.log (%LOCALAPPDATA%\Unity\Editor\Editor.log) - the live
      Editor's own log, so it works while the Editor is open and captures
      Play-mode exceptions too.
    - <repo>\Logs\*.log - local pipeline / compile-check runs.
    - <CiWorkspacePath>\Logs\*.log - the self-hosted runner's own checkout.
      A GitHub Actions self-hosted runner does NOT reuse RepoPath as its job
      workspace by default; it checks out into its own _work folder. Without
      this, a real CI failure there never shows up in this report even
      though RepoPath looks fine.

  Writes Reports/errors/latest.txt. Exits 0 whether or not errors were
  found - "no errors" is a perfectly good report.

  ASCII only, deliberately: Windows PowerShell 5.1 reads a .ps1 saved as
  UTF-8 without a BOM using the local codepage, which mangles non-ASCII
  string literals (and can break parsing outright). Korean belongs in the
  .md docs, not in these scripts.

.PARAMETER Commit
  Also commit the report when its findings changed, and push it to the fork.
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
    [string]$CiWorkspacePath = "C:\actions-runner\_work\Dory_tycoon\Dory_tycoon",
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
$hashPrefix = "Findings-Hash: "

# Reads a file another process may hold open for writing (Editor.log).
function Read-SharedFile([string]$path, [int]$tail) {
    $stream = $null
    $reader = $null
    $lines = @()

    try {
        $stream = [System.IO.File]::Open($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        $reader = New-Object System.IO.StreamReader($stream)
        $lines = $reader.ReadToEnd() -split "\r?\n"
    }
    finally {
        if ($reader) { $reader.Dispose() }
        if ($stream) { $stream.Dispose() }
    }

    if ($lines.Count -gt $tail) { return $lines[($lines.Count - $tail)..($lines.Count - 1)] }
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

        Start-Sleep -Seconds ([int][Math]::Pow(2, $attempt + 1))
        $attempt++
    }
}

function Get-TextHash([string]$text) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
        return [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace("-", "").Substring(0, 16)
    }
    finally {
        $sha.Dispose()
    }
}

$sources = @()

$editorLog = Join-Path $env:LOCALAPPDATA "Unity\Editor\Editor.log"
if (Test-Path $editorLog) { $sources += $editorLog }

$repoLogDir = Join-Path $RepoPath "Logs"
if (Test-Path $repoLogDir) {
    $sources += (Get-ChildItem -Path $repoLogDir -Filter *.log -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -ExpandProperty FullName)
}

$ciLogDir = if ($CiWorkspacePath) { Join-Path $CiWorkspacePath "Logs" } else { $null }
if ($ciLogDir -and ($ciLogDir -ne $repoLogDir) -and (Test-Path $ciLogDir)) {
    $sources += (Get-ChildItem -Path $ciLogDir -Filter *.log -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -ExpandProperty FullName)
}

if (-not $sources) {
    throw "No Unity logs found. Looked for '$editorLog', '$repoLogDir\*.log', and '$ciLogDir\*.log'."
}

$compileErrors = New-Object System.Collections.Generic.List[string]
$obsoleteWarnings = New-Object System.Collections.Generic.List[string]
$exceptions = New-Object System.Collections.Generic.List[string]
$scanned = New-Object System.Collections.Generic.List[string]

foreach ($source in $sources) {
    $lines = Read-SharedFile $source $TailLines
    $modified = (Get-Item $source).LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
    $scanned.Add("$source  (modified: $modified, lines scanned: $($lines.Count))")

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
        elseif ($trimmed -match '^\w*(Exception|Error):' -or
                $trimmed -match 'NullReferenceException|MissingReferenceException|MissingComponentException|UnassignedReferenceException') {
            if (-not $exceptions.Contains($trimmed)) { $exceptions.Add($trimmed) }
        }
    }
}

function Format-Section([string]$title, $items) {
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("## $title ($($items.Count))")
    [void]$sb.AppendLine()

    if ($items.Count -eq 0) {
        [void]$sb.AppendLine("None.")
    }
    else {
        $limit = [Math]::Min($items.Count, $MaxPerSection)
        for ($i = 0; $i -lt $limit; $i++) {
            [void]$sb.AppendLine("- $($items[$i])")
        }
        if ($items.Count -gt $MaxPerSection) {
            [void]$sb.AppendLine("- ... and $($items.Count - $MaxPerSection) more; see the raw log.")
        }
    }

    [void]$sb.AppendLine()
    return $sb.ToString()
}

# The findings are hashed on their own, so the timestamp and scan metadata
# (which differ on every single run by design) don't make an unchanged
# report look changed.
$findings = New-Object System.Text.StringBuilder
[void]$findings.Append((Format-Section "Compile errors" $compileErrors))
[void]$findings.Append((Format-Section "Obsolete API warnings (CS0618)" $obsoleteWarnings))
[void]$findings.Append((Format-Section "Runtime exceptions" $exceptions))

$findingsText = $findings.ToString()
$findingsHash = Get-TextHash $findingsText

$report = New-Object System.Text.StringBuilder
[void]$report.AppendLine("# Unity error report")
[void]$report.AppendLine()
[void]$report.AppendLine("Generated by scripts/dev/collect-errors.ps1 - do not edit by hand.")
[void]$report.AppendLine("This is how Claude Code, which has no Unity and no access to the build PC,")
[void]$report.AppendLine("reads this project's compile errors: through the repository.")
[void]$report.AppendLine()
[void]$report.AppendLine("Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
[void]$report.AppendLine("$hashPrefix$findingsHash")
[void]$report.AppendLine()
[void]$report.AppendLine("## Logs scanned")
[void]$report.AppendLine()
foreach ($entry in $scanned) { [void]$report.AppendLine("- $entry") }
[void]$report.AppendLine()
[void]$report.Append($findingsText)

$previousHash = $null
if (Test-Path $reportPath) {
    $previousHashLine = Get-Content $reportPath | Where-Object { $_.StartsWith($hashPrefix) } | Select-Object -First 1
    if ($previousHashLine) { $previousHash = $previousHashLine.Substring($hashPrefix.Length).Trim() }
}

$reportDir = Split-Path $reportPath -Parent
if (-not (Test-Path $reportDir)) { New-Item -ItemType Directory -Path $reportDir -Force | Out-Null }
Set-Content -Path $reportPath -Value $report.ToString() -Encoding UTF8

Write-Host "$($compileErrors.Count) compile error(s), $($obsoleteWarnings.Count) CS0618 warning(s), $($exceptions.Count) runtime exception(s)"
Write-Host "Report: $reportPath"

if (-not $Commit) {
    Write-Host "(Pass -Commit to push it to the fork so Claude Code can read it.)"
    exit 0
}

$isTracked = $true
try { Invoke-Git @("ls-files", "--error-unmatch", $reportRelativePath) | Out-Null }
catch { $isTracked = $false }

if ($isTracked -and $previousHash -eq $findingsHash) {
    # Nothing new to say - don't spam the history with an identical report
    # every time the scheduled sync runs.
    Invoke-Git @("checkout", "--", $reportRelativePath) | Out-Null
    Write-Host "Findings unchanged since the last report; nothing committed."
    exit 0
}

Invoke-Git @("add", $reportRelativePath) | Out-Null
Invoke-Git @("commit", "-m", "chore: update Unity error report ($($compileErrors.Count) compile error(s))") | Out-Null

if ($NoPush) {
    Write-Host "Report committed; the caller will push it."
    exit 0
}

Invoke-Git @("push", $OriginRemote, $Branch) -Retries 4 | Out-Null
Write-Host "Report pushed to the fork. Claude Code can read it now."
exit 0
