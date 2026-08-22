#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Downloads and silently installs Unity Hub on Windows.
.NOTES
  Unverified against a real Windows machine - re-check the download URL and
  installer flags against https://unity.com/download if this fails.
#>

$ErrorActionPreference = "Stop"

$hubExePath = "C:\Program Files\Unity Hub\Unity Hub.exe"
if (Test-Path $hubExePath) {
    Write-Host "Unity Hub already installed at $hubExePath - skipping."
    exit 0
}

$installerUrl = "https://public-cdn.cloud.unity3d.com/hub/prod/UnityHubSetup.exe"
$installerPath = Join-Path $env:TEMP "UnityHubSetup.exe"

Write-Host "Downloading Unity Hub installer..."
Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath

Write-Host "Running silent install..."
# /S is the standard NSIS silent-install flag Unity Hub's Windows installer uses.
Start-Process -FilePath $installerPath -ArgumentList "/S" -Wait

if (Test-Path $hubExePath) {
    Write-Host "Unity Hub installed at $hubExePath"
} else {
    Write-Warning "Unity Hub.exe not found at the expected path after install. Check $installerPath manually."
    exit 1
}
