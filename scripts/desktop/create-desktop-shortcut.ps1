<#
.SYNOPSIS
  One-time setup: creates two Desktop shortcuts, both running with no
  visible console window (just the popup dialogs). Run this once from
  PowerShell; after that, use the icons.

    "Game Factory Sync & Run"  ->  sync-and-run.ps1
        Pulls the latest work from upstream into this fork, pushes it, and
        starts a pipeline run. This is the everyday one.

    "Game Factory Run Only"    ->  run-game-factory.ps1
        Just re-runs the pipeline for a GameSpec id you type in, without
        syncing anything (useful for re-running after a flake).
#>

$ErrorActionPreference = "Stop"

$desktop = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell

function New-GameFactoryShortcut([string]$scriptName, [string]$shortcutName, [string]$description) {
    $scriptPath = Join-Path $PSScriptRoot $scriptName
    if (-not (Test-Path $scriptPath)) {
        throw "Could not find $scriptName next to this script at: $scriptPath"
    }

    $shortcutPath = Join-Path $desktop "$shortcutName.lnk"
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`""
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.Description = $description
    $shortcut.Save()

    Write-Host "Created desktop shortcut: $shortcutPath"
}

New-GameFactoryShortcut "sync-and-run.ps1" "Game Factory Sync & Run" `
    "Pull the latest work from upstream into this fork and start the Game Factory Pipeline"

New-GameFactoryShortcut "run-game-factory.ps1" "Game Factory Run Only" `
    "Trigger the Game Factory Pipeline on GitHub Actions without syncing"

Write-Host ""
Write-Host "For fully hands-off operation, also run: .\register-auto-sync.ps1"
