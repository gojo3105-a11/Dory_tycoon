<#
.SYNOPSIS
  One-time setup: creates a "Game Factory" shortcut on the Desktop that
  runs run-game-factory.ps1 with no visible console window - just the
  popup dialogs. Run this once from PowerShell; after that, use the icon.
#>

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "run-game-factory.ps1"
if (-not (Test-Path $scriptPath)) {
    throw "Could not find run-game-factory.ps1 next to this script at: $scriptPath"
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Game Factory.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`""
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = "Trigger the Game Factory Pipeline on GitHub Actions"
$shortcut.Save()

Write-Host "Created desktop shortcut: $shortcutPath"
Write-Host "Double-click it any time to trigger a Game Factory run."
