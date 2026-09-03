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
.PARAMETER Labels
  Comma-separated runner labels. The pc-control runner (see
  .github/workflows/pc-control.yml) needs "self-hosted,Windows,pc-control".
.PARAMETER WindowsLogonAccount
  Run the service as this Windows account (e.g. "DESKTOP-A7IU1E9\vasco")
  instead of NETWORK SERVICE. Required for the pc-control runner: it has to
  reach C:\Dory_tycoon, the user's stored git credentials for the fork, and
  the user's Codex login, none of which a service account has. You will be
  prompted for the account password; it is passed to config.cmd and not
  stored by this script.
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

    [string]$Labels = "self-hosted,Windows",

    [string]$WindowsLogonAccount = ""
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
    $configArgs = @("--url", $RepoUrl, "--token", $Token, "--labels", $Labels, "--unattended", "--runasservice")
    if ($WindowsLogonAccount) {
        # A second runner on the same PC must not reuse the first one's name.
        $configArgs += @("--name", "$env:COMPUTERNAME-pc-control")
        $secure = Read-Host -Prompt "Password for $WindowsLogonAccount" -AsSecureString
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
        $configArgs += @("--windowslogonaccount", $WindowsLogonAccount, "--windowslogonpassword", $plain)
    }
    & .\config.cmd @configArgs

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
