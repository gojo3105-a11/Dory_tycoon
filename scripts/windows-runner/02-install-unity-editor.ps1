#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Installs a specific Unity Editor version + Android Build Support via the
  Unity Hub CLI (headless mode).
.PARAMETER Version
  Must match ProjectSettings/ProjectVersion.txt exactly, e.g. 6000.5.9f1.
.NOTES
  Unverified against a real Windows machine. Unity Hub's CLI module names
  have changed across Hub versions (some need "android" only, older/newer
  ones split it into "android-sdk-ndk-tools" + "android-open-jdk"). If this
  script's module list fails, run:
    & $hubExe -- --headless help
  to see the module names your installed Hub version actually expects, and
  install Android Build Support manually via the Hub GUI as a fallback
  (Installs tab > your Unity version > gear icon > Add modules).
  A Unity ID must already be signed in and a license activated in Unity Hub
  (GUI, one-time, interactive) before batch-mode builds will run - this
  script only installs the Editor binaries, which does not require a
  license.
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"

$hubExe = "C:\Program Files\Unity Hub\Unity Hub.exe"
if (-not (Test-Path $hubExe)) {
    throw "Unity Hub not found at '$hubExe'. Run 01-install-unity-hub.ps1 first."
}

Write-Host "Installing Unity $Version + Android Build Support (this can take a long time)..."
& $hubExe -- --headless install --version $Version --module android --childModules

$expectedEditor = "C:\Program Files\Unity\Hub\Editor\$Version\Editor\Unity.exe"
if (Test-Path $expectedEditor) {
    Write-Host "Unity Editor installed at $expectedEditor"
} else {
    Write-Warning "Expected Unity.exe not found at '$expectedEditor'. Check Unity Hub's Installs tab for the actual result."
}
