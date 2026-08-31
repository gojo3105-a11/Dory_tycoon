#Requires -Version 5.1
<#
.SYNOPSIS
  Copies the chosen sprites out of the downloaded art packs into
  Assets/Common/Art/Runner/, refusing any pack that is not APPROVED in the
  licence registry.

.DESCRIPTION
  Reads AI_GAME_COMPANY/config/art-mapping.json and, for each target, pulls
  the named file out of the matching archive in asset_staging/_incoming/.

  The licence check is enforced HERE, in code, rather than left to whoever is
  reading the docs: a pack whose LICENSE_REGISTRY.json status is not exactly
  APPROVED is skipped with BLOCKED_LICENSE_NOT_APPROVED. Section 38 forbids
  shipping an asset with an UNKNOWN licence, and a rule that only exists in
  prose is a rule that eventually gets skipped.

  Copies only. Unity generates the prefabs and sprites from these files on
  its next Generate run; PrefabGenerator already prefers a real file over its
  procedural placeholder, per sprite.

  ASCII only, deliberately: Windows PowerShell 5.1 reads a BOM-less UTF-8
  .ps1 using the local codepage, which mangles non-ASCII string literals.

.PARAMETER DryRun
  Report what would be copied and change nothing.

.PARAMETER Commit
  Commit the copied art and push.
#>

[CmdletBinding()]
param(
    [string]$RepoPath = "C:\Dory_tycoon",
    [string]$Branch = "claude/delete-current-content-mgn4xm",
    [string]$OriginRemote = "origin",
    [switch]$DryRun,
    [switch]$Commit,
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"

$configDir = Join-Path $RepoPath "AI_GAME_COMPANY\config"
$incomingDir = Join-Path $RepoPath "AI_GAME_COMPANY\asset_staging\_incoming"
$mappingPath = Join-Path $configDir "art-mapping.json"
$registryPath = Join-Path $configDir "LICENSE_REGISTRY.json"
$workDir = Join-Path $env:TEMP "ai_game_company_assets"

foreach ($required in @($mappingPath, $registryPath)) {
    if (-not (Test-Path $required)) { throw "Missing $required - run 'git merge' first." }
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

$mapping = Get-Content $mappingPath -Raw | ConvertFrom-Json
$registry = Get-Content $registryPath -Raw | ConvertFrom-Json

# packId -> status, so the gate below is a lookup rather than a scan per target
$statusByPack = @{}
foreach ($entry in $registry.entries) { $statusByPack[$entry.id] = $entry.status }

$results = @()

foreach ($item in $mapping.targets) {
    Write-Host ""
    Write-Host "--- $($item.target) ---"

    $record = [ordered]@{
        target     = $item.target
        packId     = $item.packId
        sourceFile = $item.sourceFile
        status     = "NOT_ATTEMPTED"
        detail     = $null
    }

    $packStatus = $statusByPack[$item.packId]

    if ($packStatus -ne "APPROVED") {
        $record.status = "BLOCKED_LICENSE_NOT_APPROVED"
        $seen = if ($packStatus) { $packStatus } else { "not in registry" }
        $record.detail = "LICENSE_REGISTRY status for '$($item.packId)' is '$seen', not APPROVED. Section 38: an asset with an unverified licence does not go into a build."
        Write-Host "BLOCKED - licence status is '$seen', not APPROVED"
        $results += [pscustomobject]$record
        continue
    }

    $archivePath = Join-Path $incomingDir $item.archiveName
    if (-not (Test-Path $archivePath)) {
        $record.status = "ARCHIVE_MISSING"
        $record.detail = "Expected $archivePath. Put the pack zip back in _incoming/ and re-run."
        Write-Host "ARCHIVE_MISSING: $archivePath"
        $results += [pscustomobject]$record
        continue
    }

    $extractDir = Join-Path $workDir ([System.IO.Path]::GetFileNameWithoutExtension($item.archiveName))
    if (-not (Test-Path $extractDir)) {
        Write-Host "Extracting $($item.archiveName) ..."
        Expand-Archive -Path $archivePath -DestinationPath $extractDir -Force
    }

    # The mapping records a path relative to the pack root, but packs vary in
    # whether they nest everything one folder deep. Matching on the tail of
    # the path finds the file either way, instead of hardcoding a guess about
    # the archive's internal layout.
    $wanted = ($item.sourceFile -replace '/', '\')
    $candidates = @(Get-ChildItem -Path $extractDir -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like "*\$wanted" })

    if ($candidates.Count -eq 0) {
        $record.status = "SOURCE_FILE_NOT_FOUND"
        $record.detail = "No file matching '*\$wanted' under $extractDir. Check the pack's INVENTORY.txt for the real name."
        Write-Host "SOURCE_FILE_NOT_FOUND: $wanted"
        $results += [pscustomobject]$record
        continue
    }

    if ($candidates.Count -gt 1) {
        Write-Host "Note: $($candidates.Count) files matched; using the first."
    }

    $source = $candidates[0]
    $destination = Join-Path $RepoPath ($item.target -replace '/', '\')
    $destinationDir = Split-Path $destination -Parent

    if ($DryRun) {
        $record.status = "WOULD_COPY"
        $record.detail = "$($source.FullName) -> $destination"
        Write-Host "WOULD_COPY from $($source.FullName)"
        $results += [pscustomobject]$record
        continue
    }

    if (-not (Test-Path $destinationDir)) { New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null }
    Copy-Item $source.FullName $destination -Force

    $record.status = "COPIED"
    $record.detail = "from $($source.FullName) ($([Math]::Round($source.Length / 1KB, 1)) KB)"
    Write-Host "COPIED ($([Math]::Round($source.Length / 1KB, 1)) KB)"
    $results += [pscustomobject]$record
}

Write-Host ""
Write-Host "=== SUMMARY ==="
foreach ($result in $results) {
    Write-Host ("{0,-44} {1}" -f (Split-Path $result.target -Leaf), $result.status)
}

foreach ($skipped in $mapping.deliberatelyNotMapped) {
    Write-Host ("{0,-44} {1}" -f (Split-Path $skipped.target -Leaf), "KEPT_PLACEHOLDER (by decision)")
}

$copied = @($results | Where-Object { $_.status -eq "COPIED" })

Write-Host ""
if ($DryRun) {
    Write-Host "DRY RUN - nothing copied."
    exit 0
}

if ($copied.Count -eq 0) {
    Write-Host "Nothing was copied. See the statuses above."
    exit 0
}

Write-Host "$($copied.Count) sprite(s) in place. Unity will pick them up on the next"
Write-Host "Generate run - PrefabGenerator prefers a real file over its placeholder."

if (-not $Commit) {
    Write-Host ""
    Write-Host "(Pass -Commit to push the art.)"
    exit 0
}

Invoke-Git @("add", "--", "Assets/Common/Art") | Out-Null
$pending = Invoke-Git @("status", "--porcelain", "--", "Assets/Common/Art")
if (-not $pending) {
    Write-Host "Nothing changed; nothing committed."
    exit 0
}

Invoke-Git @("commit", "-m", "feat: use licensed CC0 art for runner ground/obstacle/coin") | Out-Null
if ($NoPush) { exit 0 }
Invoke-Git @("push", $OriginRemote, $Branch) -Retries 4 | Out-Null
Write-Host "Pushed."
exit 0
