#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Downloads, configures, and installs the GitHub Actions self-hosted runner
  as a Windows service.
.PARAMETER RepoUrl
  e.g. https://github.com/gojo3105-a11/Dory_tycoon
.PARAMETER Token
  Registration token from the repo's Settings > Actions > Runners > New
  self-hosted runner page. Expires ~1 hour after being issued - run this
  script right after generating it.
.PARAMETER InstallDir
  Where to extract the runner. Defaults to C:\actions-runner.
.NOTES
  Unverified against a real Windows machine. If the runner package's exact
  service-install command has changed, GitHub's own "New self-hosted
  runner" setup page (Settings > Actions > Runners) shows the exact,
  version-matched commands for your repo - prefer those if this diverges.
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$RepoUrl,

    [Parameter(Mandatory = $true)]
    [string]$Token,

    [string]$InstallDir = "C:\actions-runner",

    [string]$Labels = "self-hosted,Windows"
)

$ErrorActionPreference = "Stop"

Write-Host "Looking up the latest actions/runner release..."
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/actions/runner/releases/latest"
$asset = $release.assets | Where-Object { $_.name -like "actions-runner-win-x64-*.zip" } | Select-Object -First 1
if (-not $asset) {
    throw "Could not find a win-x64 runner asset in the latest actions/runner release."
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
$zipPath = Join-Path $InstallDir $asset.name

Write-Host "Downloading $($asset.name)..."
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath

Write-Host "Extracting..."
Expand-Archive -Path $zipPath -DestinationPath $InstallDir -Force

Push-Location $InstallDir
try {
    Write-Host "Configuring runner for $RepoUrl..."
    & .\config.cmd --url $RepoUrl --token $Token --labels $Labels --unattended --runasservice

    Write-Host "Verifying service..."
    Get-Service -Name "actions.runner.*" -ErrorAction SilentlyContinue | Format-Table -AutoSize
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "If no service is listed above, config.cmd may need the service installed separately:"
Write-Host "  cd $InstallDir"
Write-Host "  .\svc install"
Write-Host "  .\svc start"
Write-Host "Check the repo's Settings > Actions > Runners page - the runner should show as Idle."
