#Requires -Version 5.1
<#
.SYNOPSIS
  Downloads candidate CC0 art packs on the PC, captures each pack's OWN
  licence file as the verification evidence, and inventories what is inside -
  without importing anything into the game yet.

.DESCRIPTION
  Section 8 requires a real licence check per asset, and section 38 forbids
  shipping an asset whose licence is UNKNOWN. Claude Code cannot do this part:
  its container's egress proxy blocks kenney.nl, itch.io, opengameart.org and
  even creativecommons.org, so it cannot read a licence page or download a
  pack. This PC can.

  Capturing the licence file that ships INSIDE the archive is deliberately
  stronger evidence than reading a web page: it is the licence distributed
  with the exact bytes the game will use.

  This script does NOT decide that a pack is approved and does NOT copy art
  into Assets/. It stages, records, and stops. Claude reads the captured
  licence text from the repository, and only then is the registry updated to
  APPROVED and the art mapped in. Section 14: "AI said it is done" is not a
  PASS.

  ASCII only, deliberately: Windows PowerShell 5.1 reads a BOM-less UTF-8
  .ps1 using the local codepage, which mangles non-ASCII string literals.

.PARAMETER Pack
  Only process the pack with this id. Default: all packs in the manifest.

.PARAMETER Commit
  Commit the captured licences, inventory and report, and push.
#>

[CmdletBinding()]
param(
    [string]$RepoPath = "C:\Dory_tycoon",
    [string]$Branch = "claude/delete-current-content-mgn4xm",
    [string]$OriginRemote = "origin",
    [string]$Pack,
    [switch]$Commit,
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"

$stagingRelative = "AI_GAME_COMPANY/asset_staging"
$configRelative = "AI_GAME_COMPANY/config"
$stagingDir = Join-Path $RepoPath ($stagingRelative -replace '/', '\')
$configDir = Join-Path $RepoPath ($configRelative -replace '/', '\')
$reportPath = Join-Path $configDir "ASSET_FETCH_REPORT.json"
$downloadCache = Join-Path $env:TEMP "ai_game_company_assets"

foreach ($dir in @($stagingDir, $configDir, $downloadCache)) {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
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

# ---------------------------------------------------------------------------
# Candidate packs
#
# These are CANDIDATES, not approved assets. Nothing here is trusted until its
# shipped licence file has been captured and reviewed.
# ---------------------------------------------------------------------------

$packs = @(
    [ordered]@{
        id  = "kenney-platformer-art-deluxe"
        name = "Kenney - Platformer Art Deluxe"
        url = "https://kenney.nl/media/pages/assets/platformer-art-deluxe/6c1a2b0a5f-1677495181/kenney_platformer-art-deluxe.zip"
        expectedLicense = "CC0"
        use = "ground tiles, obstacles, coin, background elements for the Runner genre"
    },
    [ordered]@{
        id  = "kenney-background-elements"
        name = "Kenney - Background Elements"
        url = "https://kenney.nl/media/pages/assets/background-elements/8a3a0d2a3f-1677495166/kenney_background-elements.zip"
        expectedLicense = "CC0"
        use = "parallax background layers - the single biggest visual gap right now"
    }
)

if ($Pack) { $packs = @($packs | Where-Object { $_.id -eq $Pack }) }
if (-not $packs -or $packs.Count -eq 0) { throw "No packs matched '$Pack'." }

# ---------------------------------------------------------------------------

function Get-FileSha256([string]$Path) {
    return (Get-FileHash -Path $Path -Algorithm SHA256).Hash
}

$results = @()

foreach ($pack in $packs) {
    Write-Host ""
    Write-Host "=== $($pack.name) ==="

    $record = [ordered]@{
        id              = $pack.id
        name            = $pack.name
        sourceUrl       = $pack.url
        expectedLicense = $pack.expectedLicense
        intendedUse     = $pack.use
        status          = "NOT_ATTEMPTED"
        archiveSha256   = $null
        licenseFiles    = @()
        licenseAssertsCC0 = $false
        imageCount      = 0
        inventoryPath   = $null
        detail          = $null
    }

    $zipPath = Join-Path $downloadCache "$($pack.id).zip"
    $extractDir = Join-Path $downloadCache $pack.id
    $packStaging = Join-Path $stagingDir $pack.id

    try {
        if (Test-Path $zipPath) {
            Write-Host "Using cached download."
        }
        else {
            Write-Host "Downloading..."
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $pack.url -OutFile $zipPath -UseBasicParsing -TimeoutSec 300
        }

        $record.archiveSha256 = Get-FileSha256 $zipPath

        if (Test-Path $extractDir) { Remove-Item $extractDir -Recurse -Force }
        Write-Host "Extracting..."
        Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

        if (-not (Test-Path $packStaging)) { New-Item -ItemType Directory -Path $packStaging -Force | Out-Null }

        # The licence shipped inside the archive is the evidence. Without one,
        # the pack stays unusable - section 38 forbids shipping UNKNOWN.
        $licenseFiles = Get-ChildItem -Path $extractDir -Recurse -File |
            Where-Object { $_.Name -match '(?i)^(license|licence|readme|copying)' }

        foreach ($licenseFile in $licenseFiles) {
            $destName = "LICENSE_$($licenseFile.Name)"
            Copy-Item $licenseFile.FullName (Join-Path $packStaging $destName) -Force
            $record.licenseFiles += $destName

            $text = Get-Content $licenseFile.FullName -Raw -ErrorAction SilentlyContinue
            if ($text -and ($text -match '(?i)CC0' -or $text -match '(?i)public domain')) {
                $record.licenseAssertsCC0 = $true
            }
        }

        $images = Get-ChildItem -Path $extractDir -Recurse -File -Include "*.png", "*.jpg" -ErrorAction SilentlyContinue
        $record.imageCount = $images.Count

        # A full inventory so the exact files to import can be chosen from the
        # repository, instead of guessing at names that may not exist.
        $inventoryFile = Join-Path $packStaging "INVENTORY.txt"
        $relativeNames = $images | ForEach-Object { $_.FullName.Substring($extractDir.Length).TrimStart('\') }
        Set-Content -Path $inventoryFile -Value ($relativeNames -join "`r`n") -Encoding UTF8
        $record.inventoryPath = "$stagingRelative/$($pack.id)/INVENTORY.txt"

        $sourceNote = @(
            "id:          $($pack.id)",
            "name:        $($pack.name)",
            "sourceUrl:   $($pack.url)",
            "archiveSha256: $($record.archiveSha256)",
            "fetchedAt:   $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
            "fetchedBy:   AI_GAME_COMPANY/tools/fetch-cc0-assets.ps1",
            "extractedTo: $extractDir  (NOT committed - only licence + inventory are)"
        ) -join "`r`n"
        Set-Content -Path (Join-Path $packStaging "SOURCE.txt") -Value $sourceNote -Encoding UTF8

        if ($record.licenseFiles.Count -eq 0) {
            $record.status = "NO_LICENSE_FILE_FOUND"
            $record.detail = "Archive contains no licence/readme file. Cannot verify - do not import."
        }
        elseif (-not $record.licenseAssertsCC0) {
            $record.status = "LICENSE_CAPTURED_NOT_CC0"
            $record.detail = "Licence file captured but it does not assert CC0/public domain. Needs review before any use."
        }
        else {
            $record.status = "LICENSE_CAPTURED_PENDING_REVIEW"
            $record.detail = "Licence captured and mechanically asserts CC0. Still requires review before the registry is set to APPROVED."
        }

        Write-Host "$($record.status)  ($($record.imageCount) images, $($record.licenseFiles.Count) licence file(s))"
    }
    catch {
        $record.status = "FETCH_FAILED"
        $record.detail = $_.Exception.Message
        Write-Host "FETCH_FAILED: $($_.Exception.Message)"
        Write-Host "If the URL 404s the pack was probably re-versioned; download it manually"
        Write-Host "and extract into: $packStaging"
    }

    $results += [pscustomobject]$record
}

$report = [ordered]@{
    generatedAt = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    generatedBy = "AI_GAME_COMPANY/tools/fetch-cc0-assets.ps1"
    outputPath  = $reportPath
    note        = "Nothing here is APPROVED yet. Licence text and inventory are captured for review; Assets/ is untouched. Section 8 / section 38."
    results     = $results
}

Set-Content -Path $reportPath -Value ($report | ConvertTo-Json -Depth 8) -Encoding UTF8

Write-Host ""
Write-Host "=== SUMMARY ==="
foreach ($result in $results) {
    Write-Host ("{0,-32} {1}" -f $result.id, $result.status)
}
Write-Host ""
Write-Host "Report : $reportPath"
Write-Host "Staging: $stagingDir"
Write-Host ""
Write-Host "Nothing was imported into Assets/. That happens only after the"
Write-Host "captured licence text is reviewed and the registry says APPROVED."

if (-not $Commit) {
    Write-Host ""
    Write-Host "(Pass -Commit to push the captured licences and inventory.)"
    exit 0
}

Invoke-Git @("add", "--", $stagingRelative, $configRelative) | Out-Null
$pending = Invoke-Git @("status", "--porcelain", "--", $stagingRelative, $configRelative)
if (-not $pending) {
    Write-Host "Nothing changed; nothing committed."
    exit 0
}

Invoke-Git @("commit", "-m", "chore: capture CC0 asset pack licences and inventory for review") | Out-Null
if ($NoPush) { exit 0 }
Invoke-Git @("push", $OriginRemote, $Branch) -Retries 4 | Out-Null
Write-Host "Pushed."
exit 0
