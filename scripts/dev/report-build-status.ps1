#Requires -Version 5.1
<#
.SYNOPSIS
  Checks Builds/<gameId>/{APK,AAB}/ for real output files (one per
  GameSpecs/*.json) and commits a small status report, so Claude Code -
  which has no way to see GitHub Actions run results or artifacts from its
  container - can tell whether a build actually produced an APK/AAB.

.DESCRIPTION
  Scans Builds/<gameId>/ under both RepoPath (a manual/interactive clone)
  and CiWorkspacePath (the self-hosted runner's own _work checkout, which
  GitHub Actions does NOT default to RepoPath) - a successful BuildAndroid
  step on either one leaves the real file on disk, no GitHub API access
  needed to check it.

  For each file found: name, size, SHA-256 (first 16 hex chars - enough to
  notice a rebuild without hashing megabytes twice), and last-write time.
  Writes Reports/build-status/latest.txt. Commits only when the findings
  changed, like collect-errors.ps1.

.PARAMETER Commit
  Commit the report when it changed, and push it to the fork.

.PARAMETER NoPush
  With -Commit, commit locally but leave the push to the caller.
#>

[CmdletBinding()]
param(
    [string]$RepoPath = "C:\Dory_tycoon",
    [string]$CiWorkspacePath = "C:\actions-runner\_work\Dory_tycoon\Dory_tycoon",
    [string]$Branch = "claude/delete-current-content-mgn4xm",
    [string]$OriginRemote = "origin",
    [switch]$Commit,
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"

$reportRelativePath = "Reports/build-status/latest.txt"
$reportPath = Join-Path $RepoPath ($reportRelativePath -replace '/', '\')
$hashPrefix = "Findings-Hash: "

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

function Get-FileHashShort([string]$path) {
    $fullHash = (Get-FileHash -Path $path -Algorithm SHA256).Hash
    return $fullHash.Substring(0, 16)
}

function Format-Size([long]$bytes) {
    if ($bytes -ge 1MB) { return "{0:N2} MB" -f ($bytes / 1MB) }
    if ($bytes -ge 1KB) { return "{0:N1} KB" -f ($bytes / 1KB) }
    return "$bytes bytes"
}

$specsDir = Join-Path $RepoPath "GameSpecs"
if (-not (Test-Path $specsDir)) {
    throw "GameSpecs folder not found at '$specsDir'."
}

$gameIds = Get-ChildItem -Path $specsDir -Filter "*.json" -File | ForEach-Object { $_.BaseName } | Sort-Object

# A GitHub Actions self-hosted runner does NOT reuse RepoPath as its job
# workspace by default - it checks out into its own _work folder - so a
# real build there never showed up here unless we also scan CiWorkspacePath.
$scanRoots = @(@{ Label = "RepoPath"; Path = $RepoPath })
if ($CiWorkspacePath -and ($CiWorkspacePath -ne $RepoPath) -and (Test-Path $CiWorkspacePath)) {
    $scanRoots += @{ Label = "CiWorkspacePath"; Path = $CiWorkspacePath }
}

$lines = New-Object System.Collections.Generic.List[string]
$anyBuild = $false

foreach ($gameId in $gameIds) {
    [void]$lines.Add("## $gameId")
    [void]$lines.Add("")

    $entries = New-Object System.Collections.Generic.List[string]

    foreach ($root in $scanRoots) {
        $gameBuildDir = Join-Path $root.Path "Builds\$gameId"
        if (-not (Test-Path $gameBuildDir)) { continue }

        $outputs = Get-ChildItem -Path $gameBuildDir -Recurse -File -Include "*.apk", "*.aab" -ErrorAction SilentlyContinue
        foreach ($file in ($outputs | Sort-Object LastWriteTime -Descending)) {
            $relative = $file.FullName.Substring($root.Path.Length).TrimStart('\')
            $size = Format-Size $file.Length
            $modified = $file.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
            $hash = Get-FileHashShort $file.FullName
            $entries.Add("- [$($root.Label)] $relative  ($size, sha256:$hash, built $modified)")
        }
    }

    if ($entries.Count -eq 0) {
        $checkedPaths = ($scanRoots | ForEach-Object { $_.Path }) -join ", "
        [void]$lines.Add("No .apk/.aab found under Builds\$gameId\ (checked: $checkedPaths).")
    }
    else {
        $anyBuild = $true
        foreach ($entry in $entries) { [void]$lines.Add($entry) }
    }

    [void]$lines.Add("")
}

$findingsText = ($lines -join "`n") + "`n"
$findingsHash = Get-TextHash $findingsText

$report = New-Object System.Text.StringBuilder
[void]$report.AppendLine("# Build status report")
[void]$report.AppendLine()
[void]$report.AppendLine("Generated by scripts/dev/report-build-status.ps1 - do not edit by hand.")
[void]$report.AppendLine("Scans Builds/<gameId>/ on this machine for real .apk/.aab files, since")
[void]$report.AppendLine("Claude Code has no GitHub Actions API access to check artifacts directly.")
[void]$report.AppendLine()
[void]$report.AppendLine("Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
[void]$report.AppendLine("$hashPrefix$findingsHash")
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

Write-Host "Scanned $($gameIds.Count) GameSpec(s); build output found: $anyBuild"
Write-Host "Report: $reportPath"

if (-not $Commit) {
    Write-Host "(Pass -Commit to push it to the fork so Claude Code can read it.)"
    exit 0
}

$isTracked = $true
try { Invoke-Git @("ls-files", "--error-unmatch", $reportRelativePath) | Out-Null }
catch { $isTracked = $false }

if ($isTracked -and $previousHash -eq $findingsHash) {
    Invoke-Git @("checkout", "--", $reportRelativePath) | Out-Null
    Write-Host "Findings unchanged since the last report; nothing committed."
    exit 0
}

Invoke-Git @("add", $reportRelativePath) | Out-Null
Invoke-Git @("commit", "-m", "chore: update build status report") | Out-Null

if ($NoPush) {
    Write-Host "Report committed; the caller will push it."
    exit 0
}

Invoke-Git @("push", $OriginRemote, $Branch) -Retries 4 | Out-Null
Write-Host "Report pushed to the fork. Claude Code can read it now."
exit 0
