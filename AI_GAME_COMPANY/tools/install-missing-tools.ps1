#Requires -Version 5.1
<#
.SYNOPSIS
  Installs the free tools the AI GAME COMPANY pipeline needs and that are
  missing from this PC, then records exactly what happened.

.DESCRIPTION
  Implements master prompt section 43: "additional components installable at
  no cost - make an install plan and proceed as far as possible. When payment
  would be required, do not proceed automatically; record PAID_ACTION_BLOCKED."

  Deliberately NOT auto-installed (see company_policy.json never_auto_install):

    Unity           - licence tier, plus section 19: the verified APK Baseline
                      depends on the exact installed editor version. Installing
                      or upgrading Unity automatically could break the one
                      pipeline that is currently known to work.
    Ollama MODELS   - sections 4 and 8. The Ollama SERVER is free and gets
                      installed; the model WEIGHTS are separately licensed and
                      "it is a Qwen" is explicitly not sufficient to assume a
                      licence. Models are pulled only after their specific
                      model ID is APPROVED in LICENSE_REGISTRY.json.
    ComfyUI / image / image-to-3d models
                    - section 9: the exact repository licence must be read
                      before installation.
    Anything paid   - recorded as PAID_ACTION_BLOCKED, never purchased.

  Logins (Claude, Codex) are HUMAN_GATE per section 37: the CLI is installed
  automatically, but signing in is left to the user.

  Package IDs are NOT assumed to exist. Each one is looked up in the package
  manager first, because section 38 forbids guessing at commands and IDs that
  may not be valid on this machine.

  ASCII only, deliberately: Windows PowerShell 5.1 reads a BOM-less UTF-8
  .ps1 using the local codepage, which mangles non-ASCII string literals.

.PARAMETER DryRun
  Report what would be installed and change nothing. Run this first.

.PARAMETER Commit
  Commit the install report and push it so Claude Code can read it.
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

$companyRelative = "AI_GAME_COMPANY"
$configRelative = "$companyRelative/config"
$configDir = Join-Path $RepoPath ($configRelative -replace '/', '\')
$logDir = Join-Path $RepoPath ($companyRelative -replace '/', '\') | Join-Path -ChildPath "logs"
$reportPath = Join-Path $configDir "INSTALL_REPORT.json"
$policyPath = Join-Path $configDir "company_policy.json"

foreach ($dir in @($configDir, $logDir)) {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
}

$logPath = Join-Path $logDir "install-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

function Write-Log {
    param([string]$Message)
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $Message"
    Write-Host $line
    Add-Content -Path $logPath -Value $line -Encoding UTF8
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

# Newly installed tools land on the machine/user PATH, but this process still
# has the PATH it started with - without this refresh every post-install probe
# would wrongly report the tool as still missing.
function Update-SessionPath {
    $machine = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = (@($machine, $user) | Where-Object { $_ }) -join ";"
}

function Test-ToolPresent {
    param([string[]]$Commands)
    foreach ($command in $Commands) {
        if (Get-Command $command -ErrorAction SilentlyContinue) { return $true }
    }
    return $false
}

function Invoke-External {
    param([string]$Exe, [string[]]$Arguments, [int]$TimeoutSeconds = 900)

    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $Exe @Arguments 2>&1 | Out-String
        return [pscustomobject]@{ exitCode = $LASTEXITCODE; output = $output.Trim() }
    }
    catch {
        return [pscustomobject]@{ exitCode = -1; output = $_.Exception.Message }
    }
    finally {
        $ErrorActionPreference = $previous
    }
}

# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

$policy = $null
if (Test-Path $policyPath) {
    $policy = Get-Content $policyPath -Raw | ConvertFrom-Json
}
else {
    Write-Log "WARNING: company_policy.json not found at $policyPath - refusing to install anything."
}

$autoInstallAllowed = $false
if ($policy -and $policy.allow_auto_install_free_tools) { $autoInstallAllowed = $true }

Write-Log "AI GAME COMPANY - install missing free tools"
Write-Log "Policy allow_auto_install_free_tools = $autoInstallAllowed"
if ($DryRun) { Write-Log "DRY RUN - nothing will be installed." }

# ---------------------------------------------------------------------------
# Package manager
# ---------------------------------------------------------------------------

Update-SessionPath
$wingetPresent = Test-ToolPresent -Commands @("winget")

if (-not $wingetPresent) {
    Write-Log "winget NOT FOUND. It ships with the App Installer from the Microsoft Store."
    Write-Log "Install 'App Installer' from the Microsoft Store, then re-run this script."
}

# ---------------------------------------------------------------------------
# Tool manifest
# ---------------------------------------------------------------------------

$tools = @(
    [ordered]@{
        id = "git"; display = "Git"; probe = @("git")
        method = "winget"; packageId = "Git.Git"
        autoInstall = $true; gate = $null
        why = "Required for the whole report/sync loop."
    },
    [ordered]@{
        id = "python"; display = "Python 3"; probe = @("python", "python3", "py")
        method = "winget"; packageId = "Python.Python.3.12"
        autoInstall = $true; gate = $null
        why = "The orchestrator (section 13) is Python."
    },
    [ordered]@{
        id = "node"; display = "Node.js LTS"; probe = @("node")
        method = "winget"; packageId = "OpenJS.NodeJS.LTS"
        autoInstall = $true; gate = $null
        why = "Needed to install the Codex and Claude Code CLIs via npm."
    },
    [ordered]@{
        id = "ollama"; display = "Ollama (server only)"; probe = @("ollama")
        method = "winget"; packageId = "Ollama.Ollama"
        autoInstall = $true; gate = $null
        why = "Local LLM gateway (section 4). The SERVER is free; MODELS are NOT auto-pulled - each model ID needs its own licence check (sections 4, 8)."
    },
    [ordered]@{
        id = "blender"; display = "Blender"; probe = @("blender")
        method = "winget"; packageId = "BlenderFoundation.Blender"
        autoInstall = $true; gate = $null
        why = "3D post-processing via background Python scripts (section 11)."
    },
    [ordered]@{
        id = "codex"; display = "Codex CLI"; probe = @("codex")
        method = "npm"; packageId = "@openai/codex"
        autoInstall = $true; gate = "LOGIN_REQUIRED"
        why = "Independent code review (section 3). Installing is free; signing in is a HUMAN_GATE (section 37)."
    },
    [ordered]@{
        id = "claude"; display = "Claude Code CLI"; probe = @("claude")
        method = "npm"; packageId = "@anthropic-ai/claude-code"
        autoInstall = $true; gate = "LOGIN_REQUIRED"
        why = "Section 2 requires reading its real --help to decide whether headless subprocess calls are even supported. Signing in is a HUMAN_GATE."
    },
    [ordered]@{
        id = "unity"; display = "Unity Editor"; probe = @()
        method = "none"; packageId = $null
        autoInstall = $false; gate = "HUMAN_GATE"
        why = "NEVER auto-installed. Licence tier plus section 19: the verified APK Baseline depends on the exact installed editor version, and an automatic install/upgrade could break the only pipeline currently known to work."
    },
    [ordered]@{
        id = "ollama_models"; display = "Ollama models"; probe = @()
        method = "none"; packageId = $null
        autoInstall = $false; gate = "LICENSE_CHECK_REQUIRED"
        why = "NEVER auto-pulled. Sections 4 and 8: each specific model ID's licence must be verified and marked APPROVED in LICENSE_REGISTRY.json first. 'It is a Qwen' or 'it is a DeepSeek' is explicitly not sufficient."
    },
    [ordered]@{
        id = "comfyui"; display = "ComfyUI + image models"; probe = @()
        method = "none"; packageId = $null
        autoInstall = $false; gate = "LICENSE_CHECK_REQUIRED"
        why = "NEVER auto-installed. Section 9: the exact model repository licence must be read before installation."
    }
)

# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

$results = @()

foreach ($tool in $tools) {
    $record = [ordered]@{
        id       = $tool.id
        display  = $tool.display
        expected = "available on PATH"
        actual   = $null
        status   = "NOT_ATTEMPTED"
        method   = $tool.method
        packageId = $tool.packageId
        why      = $tool.why
        detail   = $null
    }

    Write-Log ""
    Write-Log "--- $($tool.display) ---"

    $present = $false
    if ($tool.probe.Count -gt 0) {
        $present = Test-ToolPresent -Commands $tool.probe
    }

    if ($present) {
        $record.actual = "present"
        $record.status = "ALREADY_INSTALLED"
        if ($tool.gate -eq "LOGIN_REQUIRED") {
            $record.status = "ALREADY_INSTALLED"
            $record.detail = "Installed. Login state is a HUMAN_GATE - not checked or performed here."
        }
        Write-Log "ALREADY_INSTALLED"
        $results += [pscustomobject]$record
        continue
    }

    if (-not $tool.autoInstall) {
        $record.actual = "not installed"
        $record.status = $tool.gate
        $record.detail = $tool.why
        Write-Log "$($tool.gate) - deliberately not auto-installed."
        $results += [pscustomobject]$record
        continue
    }

    if (-not $autoInstallAllowed) {
        $record.actual = "not installed"
        $record.status = "SKIPPED_POLICY"
        $record.detail = "company_policy.json allow_auto_install_free_tools is false."
        Write-Log "SKIPPED_POLICY"
        $results += [pscustomobject]$record
        continue
    }

    if ($tool.method -eq "winget" -and -not $wingetPresent) {
        $record.actual = "not installed"
        $record.status = "BLOCKED_NO_PACKAGE_MANAGER"
        $record.detail = "winget is unavailable. Install 'App Installer' from the Microsoft Store."
        Write-Log "BLOCKED_NO_PACKAGE_MANAGER"
        $results += [pscustomobject]$record
        continue
    }

    if ($tool.method -eq "npm" -and -not (Test-ToolPresent -Commands @("npm"))) {
        $record.actual = "not installed"
        $record.status = "BLOCKED_MISSING_DEPENDENCY"
        $record.detail = "npm is not available yet (Node.js install may need a new shell). Re-run this script."
        Write-Log "BLOCKED_MISSING_DEPENDENCY - npm missing"
        $results += [pscustomobject]$record
        continue
    }

    if ($DryRun) {
        $record.actual = "not installed"
        $record.status = "WOULD_INSTALL"
        $record.detail = "$($tool.method) : $($tool.packageId)"
        Write-Log "WOULD_INSTALL via $($tool.method): $($tool.packageId)"
        $results += [pscustomobject]$record
        continue
    }

    if ($tool.method -eq "winget") {
        # Section 38: do not assume the package ID is valid on this machine.
        # Look it up first and record a clear NOT_FOUND instead of firing off
        # an install for something that may not exist.
        Write-Log "Verifying package id exists: $($tool.packageId)"
        $search = Invoke-External -Exe "winget" -Arguments @(
            "search", "--id", $tool.packageId, "--exact",
            "--accept-source-agreements", "--disable-interactivity")

        if ($search.exitCode -ne 0 -or $search.output -match "No package found") {
            $record.actual = "not installed"
            $record.status = "PACKAGE_ID_NOT_FOUND"
            $record.detail = "winget search found no exact match for '$($tool.packageId)'. Needs a manual install or a corrected id."
            Write-Log "PACKAGE_ID_NOT_FOUND"
            $results += [pscustomobject]$record
            continue
        }

        Write-Log "Installing $($tool.packageId) ..."
        $install = Invoke-External -Exe "winget" -Arguments @(
            "install", "--id", $tool.packageId, "--exact", "--silent",
            "--accept-source-agreements", "--accept-package-agreements",
            "--disable-interactivity")
        $record.detail = "winget exit $($install.exitCode)"
        Add-Content -Path $logPath -Value $install.output -Encoding UTF8
    }
    elseif ($tool.method -eq "npm") {
        Write-Log "Installing $($tool.packageId) via npm ..."
        $install = Invoke-External -Exe "npm" -Arguments @("install", "-g", $tool.packageId)
        $record.detail = "npm exit $($install.exitCode)"
        Add-Content -Path $logPath -Value $install.output -Encoding UTF8
    }

    Update-SessionPath
    $nowPresent = Test-ToolPresent -Commands $tool.probe

    if ($nowPresent) {
        $record.actual = "present"
        $record.status = "INSTALLED"
        if ($tool.gate -eq "LOGIN_REQUIRED") {
            $record.detail = "Installed. Sign-in is still required and is a HUMAN_GATE (section 37)."
        }
        Write-Log "INSTALLED"
    }
    else {
        $record.actual = "still missing"
        $record.status = "FAILED"
        if (-not $record.detail) { $record.detail = "Install reported no error but the command is still not on PATH." }
        $record.detail += " A new terminal (or admin rights) may be required."
        Write-Log "FAILED - still not on PATH"
    }

    $results += [pscustomobject]$record
}

# ---------------------------------------------------------------------------
# Report (section 43: EXPECTED / ACTUAL / STATUS / LOG_PATH / OUTPUT_PATH)
# ---------------------------------------------------------------------------

$loginGates = @($results | Where-Object { $_.detail -and $_.detail -match "HUMAN_GATE" } | ForEach-Object { $_.id })

$report = [ordered]@{
    generatedAt = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    generatedBy = "AI_GAME_COMPANY/tools/install-missing-tools.ps1"
    dryRun      = [bool]$DryRun
    machineName = $env:COMPUTERNAME
    logPath     = $logPath
    outputPath  = $reportPath
    policy = [ordered]@{
        allow_auto_install_free_tools = $autoInstallAllowed
        allow_paid_api                = if ($policy) { $policy.allow_paid_api } else { $null }
        allow_auto_purchase           = if ($policy) { $policy.allow_auto_purchase } else { $null }
    }
    packageManager = [ordered]@{ winget = $wingetPresent }
    autoAcceptedAgreements = @(
        "winget source agreements (--accept-source-agreements)",
        "winget package agreements for the free OSS packages listed in results (--accept-package-agreements)"
    )
    results = $results
    humanGatesRemaining = $loginGates
    paidActionsBlocked = @()
}

Set-Content -Path $reportPath -Value ($report | ConvertTo-Json -Depth 8) -Encoding UTF8

Write-Log ""
Write-Log "=== SUMMARY ==="
foreach ($result in $results) {
    Write-Log ("{0,-16} {1}" -f $result.id, $result.status)
}
Write-Log ""
Write-Log "Report: $reportPath"
Write-Log "Log   : $logPath"
Write-Log ""
Write-Log "NEXT: run detect-environment.ps1 so adapters get built against what is actually installed."

if (-not $Commit) {
    Write-Host ""
    Write-Host "(Pass -Commit to push the install report so Claude Code can read it.)"
    exit 0
}

Invoke-Git @("add", "--", $configRelative) | Out-Null
$pending = Invoke-Git @("status", "--porcelain", "--", $configRelative)
if (-not $pending) {
    Write-Log "Nothing changed; nothing committed."
    exit 0
}

Invoke-Git @("commit", "-m", "chore: update AI_GAME_COMPANY install report") | Out-Null
if ($NoPush) { exit 0 }
Invoke-Git @("push", $OriginRemote, $Branch) -Retries 4 | Out-Null
Write-Log "Pushed."
exit 0
