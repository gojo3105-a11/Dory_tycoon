#Requires -Version 5.1
<#
.SYNOPSIS
  Captures the licence and file inventory of art-pack archives on the PC, so
  a pack can be licence-verified before any of it is imported into the game.

.DESCRIPTION
  Section 8 requires a real licence check per asset and section 38 forbids
  shipping an asset whose licence is UNKNOWN. Claude Code cannot do this part:
  its container's egress proxy blocks kenney.nl, itch.io, opengameart.org and
  even creativecommons.org, so it can neither read a licence page nor download
  a pack.

  Capturing the licence file that ships INSIDE the archive is deliberately
  stronger evidence than reading a web page: it is the licence distributed
  with the exact bytes the game will use.

  HOW ARCHIVES GET HERE
    Default: drop the .zip files into
      AI_GAME_COMPANY/asset_staging/_incoming/
    and run this with no arguments. Every zip there is processed.

    Earlier versions of this script hardcoded download URLs. Those URLs were
    guesses - the sites are unreachable from the container that wrote them -
    and section 38 forbids guessing. So downloading is now opt-in via -Url,
    and the normal path is a file you fetched yourself in a browser.

  This script does NOT decide that a pack is approved and does NOT copy art
  into Assets/. It stages evidence and stops. Section 14: "the AI said it is
  done" is not a PASS.

  ASCII only, deliberately: Windows PowerShell 5.1 reads a BOM-less UTF-8
  .ps1 using the local codepage, which mangles non-ASCII string literals.

.PARAMETER Url
  Optional. Download this archive instead of reading the drop folder. Use it
  only with a URL you have confirmed works.

.PARAMETER PackId
  Optional id for the -Url download. Defaults to the file name.

.PARAMETER Commit
  Commit the captured licences, inventory and report, and push.
#>

[CmdletBinding()]
param(
    [string]$RepoPath = "C:\Dory_tycoon",
    [string]$Branch = "claude/delete-current-content-mgn4xm",
    [string]$OriginRemote = "origin",
    [string]$Url,
    [string]$PackId,
    [switch]$Commit,
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"

$stagingRelative = "AI_GAME_COMPANY/asset_staging"
$configRelative = "AI_GAME_COMPANY/config"
$stagingDir = Join-Path $RepoPath ($stagingRelative -replace '/', '\')
$configDir = Join-Path $RepoPath ($configRelative -replace '/', '\')
$incomingDir = Join-Path $stagingDir "_incoming"
$reportPath = Join-Path $configDir "ASSET_FETCH_REPORT.json"
$workDir = Join-Path $env:TEMP "ai_game_company_assets"

foreach ($dir in @($stagingDir, $configDir, $incomingDir, $workDir)) {
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
# Collect the archives to process
# ---------------------------------------------------------------------------

$archives = @()

if ($Url) {
    $downloadId = $PackId
    if (-not $downloadId) {
        $downloadId = [System.IO.Path]::GetFileNameWithoutExtension(([Uri]$Url).LocalPath)
    }
    if (-not $downloadId) { $downloadId = "downloaded-pack" }

    $target = Join-Path $incomingDir "$downloadId.zip"
    Write-Host "Downloading $Url"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $Url -OutFile $target -UseBasicParsing -TimeoutSec 300
        $archives += Get-Item $target
    }
    catch {
        Write-Host "Download failed: $($_.Exception.Message)"
        exit 1
    }
}
else {
    $archives = @(Get-ChildItem -Path $incomingDir -Filter "*.zip" -File -ErrorAction SilentlyContinue)
}

if ($archives.Count -eq 0) {
    Write-Host ""
    Write-Host "No archives to process."
    Write-Host ""
    Write-Host "Download the art packs in a browser, then drop the .zip files into:"
    Write-Host "  $incomingDir"
    Write-Host ""
    Write-Host "and run this script again. Nothing else is needed - the licence"
    Write-Host "file inside each zip is what gets captured as evidence."
    exit 0
}

Write-Host "Found $($archives.Count) archive(s) to process."

# ---------------------------------------------------------------------------
# Process each archive
# ---------------------------------------------------------------------------

$results = @()

foreach ($archive in $archives) {
    $archiveId = $archive.BaseName
    Write-Host ""
    Write-Host "=== $archiveId ==="

    $record = [ordered]@{
        id                = $archiveId
        archiveName       = $archive.Name
        archiveSizeMb     = [Math]::Round($archive.Length / 1MB, 2)
        archiveSha256     = $null
        sourceUrl         = $Url
        status            = "NOT_ATTEMPTED"
        licenseFiles      = @()
        licenseAssertsCC0 = $false
        imageCount        = 0
        inventoryPath     = $null
        detail            = $null
    }

    $extractDir = Join-Path $workDir $archiveId
    $packStaging = Join-Path $stagingDir $archiveId

    try {
        $record.archiveSha256 = (Get-FileHash -Path $archive.FullName -Algorithm SHA256).Hash

        if (Test-Path $extractDir) { Remove-Item $extractDir -Recurse -Force }
        Write-Host "Extracting..."
        Expand-Archive -Path $archive.FullName -DestinationPath $extractDir -Force

        if (-not (Test-Path $packStaging)) { New-Item -ItemType Directory -Path $packStaging -Force | Out-Null }

        # The licence shipped inside the archive is the evidence. Without one
        # the pack stays unusable - section 38 forbids shipping UNKNOWN.
        $licenseFiles = @(Get-ChildItem -Path $extractDir -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '(?i)^(license|licence|readme|copying)' })

        foreach ($licenseFile in $licenseFiles) {
            $destName = "LICENSE_$($licenseFile.Name)"
            Copy-Item $licenseFile.FullName (Join-Path $packStaging $destName) -Force
            $record.licenseFiles += $destName

            $text = Get-Content $licenseFile.FullName -Raw -ErrorAction SilentlyContinue
            if ($text -and ($text -match '(?i)CC0' -or $text -match '(?i)public domain')) {
                $record.licenseAssertsCC0 = $true
            }
        }

        $images = @(Get-ChildItem -Path $extractDir -Recurse -File -Include "*.png", "*.jpg" -ErrorAction SilentlyContinue)
        $record.imageCount = $images.Count

        # A full inventory so the exact files to import can be chosen from the
        # repository, instead of guessing at names that may not exist.
        $inventoryFile = Join-Path $packStaging "INVENTORY.txt"

        # Resolve-Path first: $env:TEMP often hands back an 8.3 short path
        # ("VASCO-~1") while Get-ChildItem returns the long form, so a naive
        # Substring($extractDir.Length) cuts the wrong number of characters
        # and silently mangles every entry. Anything that still does not sit
        # under the root keeps its absolute path rather than being truncated.
        $extractRoot = (Resolve-Path $extractDir).ProviderPath.TrimEnd('\')
        $relativeNames = @($images | ForEach-Object {
            if ($_.FullName.StartsWith($extractRoot, [StringComparison]::OrdinalIgnoreCase)) {
                $_.FullName.Substring($extractRoot.Length).TrimStart('\')
            }
            else {
                $_.FullName
            }
        })
        Set-Content -Path $inventoryFile -Value ($relativeNames -join "`r`n") -Encoding UTF8
        $record.inventoryPath = "$stagingRelative/$archiveId/INVENTORY.txt"

        $sourceLines = @(
            "id:            $archiveId",
            "archiveName:   $($archive.Name)",
            "archiveSha256: $($record.archiveSha256)",
            "sourceUrl:     $(if ($Url) { $Url } else { 'manually downloaded into _incoming/' })",
            "fetchedAt:     $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
            "fetchedBy:     AI_GAME_COMPANY/tools/fetch-cc0-assets.ps1",
            "extractedTo:   $extractDir  (NOT committed - only licence + inventory are)"
        )
        Set-Content -Path (Join-Path $packStaging "SOURCE.txt") -Value ($sourceLines -join "`r`n") -Encoding UTF8

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
        $record.status = "PROCESSING_FAILED"
        $record.detail = $_.Exception.Message
        Write-Host "PROCESSING_FAILED: $($_.Exception.Message)"
    }

    $results += [pscustomobject]$record
}

$report = [ordered]@{
    generatedAt = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    generatedBy = "AI_GAME_COMPANY/tools/fetch-cc0-assets.ps1"
    outputPath  = $reportPath
    incomingDir = $incomingDir
    note        = "Nothing here is APPROVED yet. Licence text and inventory are captured for review; Assets/ is untouched. Section 8 / section 38."
    results     = $results
}

Set-Content -Path $reportPath -Value ($report | ConvertTo-Json -Depth 8) -Encoding UTF8

Write-Host ""
Write-Host "=== SUMMARY ==="
foreach ($result in $results) {
    Write-Host ("{0,-40} {1}" -f $result.id, $result.status)
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

Invoke-Git @("commit", "-m", "chore: capture art pack licences and inventory for review") | Out-Null
if ($NoPush) { exit 0 }
Invoke-Git @("push", $OriginRemote, $Branch) -Retries 4 | Out-Null
Write-Host "Pushed."
exit 0
