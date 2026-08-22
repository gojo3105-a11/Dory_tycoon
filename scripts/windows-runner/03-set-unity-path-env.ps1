#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Finds an installed Unity.exe and sets it as the machine-wide UNITY_PATH
  environment variable that .github/workflows/*.yml expect.
.PARAMETER Version
  Optional. If omitted, uses whichever single Unity install is found under
  C:\Program Files\Unity\Hub\Editor\ (errors if there is more than one -
  pass -Version to disambiguate).
#>

param(
    [string]$Version
)

$ErrorActionPreference = "Stop"

$editorRoot = "C:\Program Files\Unity\Hub\Editor"
if (-not (Test-Path $editorRoot)) {
    throw "No Unity installations found under '$editorRoot'. Run 02-install-unity-editor.ps1 first."
}

if ($Version) {
    $unityExe = Join-Path $editorRoot "$Version\Editor\Unity.exe"
    if (-not (Test-Path $unityExe)) {
        throw "Unity.exe not found at '$unityExe'."
    }
} else {
    $candidates = Get-ChildItem -Path $editorRoot -Directory | ForEach-Object {
        Join-Path $_.FullName "Editor\Unity.exe"
    } | Where-Object { Test-Path $_ }

    if ($candidates.Count -eq 0) {
        throw "No Unity.exe found under '$editorRoot'."
    }
    if ($candidates.Count -gt 1) {
        Write-Host "Multiple Unity installs found:"
        $candidates | ForEach-Object { Write-Host "  $_" }
        throw "Pass -Version to pick one (must match ProjectSettings/ProjectVersion.txt)."
    }

    $unityExe = $candidates[0]
}

[Environment]::SetEnvironmentVariable("UNITY_PATH", $unityExe, "Machine")
Write-Host "UNITY_PATH set to: $unityExe"
Write-Host "Open a new terminal (or restart the runner service) for this to take effect there."
