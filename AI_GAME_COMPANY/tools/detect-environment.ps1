#Requires -Version 5.1
<#
.SYNOPSIS
  Surveys this PC for everything the AI GAME COMPANY pipeline depends on and
  writes the result into the repository, so Claude Code (which runs in a
  Linux container with no Unity, no GPU, no Ollama and no Codex) can build
  adapters against what is ACTUALLY installed instead of guessing.

.DESCRIPTION
  Implements master prompt sections 6 and 41 STEP 3-5.

  Writes:
    AI_GAME_COMPANY/config/HARDWARE_PROFILE.json  - machine + tool inventory
    AI_GAME_COMPANY/config/cli-probes/<tool>.txt  - RAW --help / --version text

  The raw probe files matter as much as the JSON: section 41 STEP 5 requires
  that only CLI commands actually supported by the installed versions get
  wired into adapters, and section 38 forbids guessing at commands that may
  not exist. Claude reads these files to write correct adapters.

  SECURITY (section 3):
    - Never writes the VALUE of any API key or token; only whether the
      environment variable is present, because section 7 needs to know a key
      exists in order to deliberately NOT use it.
    - Never reads or copies auth files such as ~/.codex/auth.json.
    - Login state is probed only through each CLI's own status command.

  ASCII only, deliberately: Windows PowerShell 5.1 reads a BOM-less UTF-8
  .ps1 using the local codepage, which mangles non-ASCII string literals and
  can break parsing outright. Korean belongs in the .md docs.

.PARAMETER Commit
  Commit the profile and probe files and push them to the fork, which is how
  Claude Code gets to see them.

.PARAMETER NoPush
  With -Commit, commit locally and leave the push to the caller.
#>

[CmdletBinding()]
param(
    [string]$RepoPath = "C:\Dory_tycoon",
    [string]$Branch = "claude/delete-current-content-mgn4xm",
    [string]$OriginRemote = "origin",
    [string]$OllamaUrl = "http://localhost:11434",
    [switch]$Commit,
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"

$companyRelative = "AI_GAME_COMPANY"
$configRelative = "$companyRelative/config"
$probeRelative = "$configRelative/cli-probes"

$configDir = Join-Path $RepoPath ($configRelative -replace '/', '\')
$probeDir = Join-Path $RepoPath ($probeRelative -replace '/', '\')
$profilePath = Join-Path $configDir "HARDWARE_PROFILE.json"

foreach ($dir in @($configDir, $probeDir)) {
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

# Runs a command and captures stdout+stderr without letting a non-zero exit
# code or a missing executable abort the whole survey. A tool that is absent
# is a finding, not a crash.
function Invoke-Probe {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [int]$TimeoutSeconds = 25
    )

    $result = [ordered]@{
        ran      = $false
        exitCode = $null
        output   = ""
        error    = ""
    }

    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $stdOutFile = [System.IO.Path]::GetTempFileName()
        $stdErrFile = [System.IO.Path]::GetTempFileName()

        # -ArgumentList refuses an empty array in PowerShell 5.1, so it is
        # only supplied when there is actually something to pass.
        $startArgs = @{
            FilePath               = $FilePath
            NoNewWindow            = $true
            PassThru               = $true
            RedirectStandardOutput = $stdOutFile
            RedirectStandardError  = $stdErrFile
        }
        if ($Arguments -and $Arguments.Count -gt 0) { $startArgs.ArgumentList = $Arguments }

        # npm installs its global CLIs as shims. Start-Process can launch a
        # .cmd shim but NOT a .ps1 one - it has no associated executable
        # handler - which is why 'claude' and 'codex' first came back as
        # FOUND_BUT_NOT_RUNNABLE. Route those through cmd.exe instead.
        if ($FilePath -match '\.ps1$') {
            $startArgs.FilePath = "$env:ComSpec"
            $shimName = [System.IO.Path]::GetFileNameWithoutExtension($FilePath)
            $startArgs.ArgumentList = @("/c", $shimName) + $Arguments
        }

        $process = Start-Process @startArgs

        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try { $process.Kill() } catch { }
            $result.error = "timed out after ${TimeoutSeconds}s"
            return [pscustomobject]$result
        }

        $result.ran = $true
        $result.exitCode = $process.ExitCode
        $result.output = (Get-Content $stdOutFile -Raw -ErrorAction SilentlyContinue)
        $result.error = (Get-Content $stdErrFile -Raw -ErrorAction SilentlyContinue)
    }
    catch {
        $result.error = $_.Exception.Message
    }
    finally {
        $ErrorActionPreference = $previous
        Remove-Item $stdOutFile, $stdErrFile -ErrorAction SilentlyContinue
    }

    return [pscustomobject]$result
}

function Save-Probe {
    param([string]$Name, [string]$Title, [string]$Body)

    $path = Join-Path $probeDir "$Name.txt"
    $header = "# $Title`r`n# captured: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`r`n" + ("-" * 70) + "`r`n"
    Set-Content -Path $path -Value ($header + $Body) -Encoding UTF8
}

# Detects one CLI tool: where it is, what version it reports, and - most
# importantly for section 41 STEP 5 - its raw help text.
function Get-ToolInfo {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Commands,
        [string[]]$VersionArgs = @("--version"),
        [string[]]$HelpArgs = @("--help"),
        [hashtable]$ExtraProbes = @{},
        [string[]]$ExtraPaths = @()
    )

    $info = [ordered]@{
        name      = $Name
        installed = $false
        path      = $null
        version   = $null
        status    = "NOT_FOUND"
        notes     = @()
    }

    # Try EVERY candidate and keep the first that reports a real version,
    # rather than the first that merely exists on PATH.
    #
    # Windows ships "app execution aliases" under WindowsApps: stubs that exist,
    # are executable, and only print "Python was not found; run without
    # arguments to install from the Microsoft Store". Taking the first PATH hit
    # reported python as installed and runnable when no Python existed at all -
    # and the installer then skipped it as ALREADY_INSTALLED.
    $resolvedPath = $null
    $stubsSkipped = @()

    foreach ($command in $Commands) {
        $found = Get-Command $command -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $found) { continue }

        $candidate = $found.Source
        if (-not $candidate) { $candidate = $found.Name }

        if ($candidate -like "*\WindowsApps\*") {
            $stubCheck = Invoke-Probe -FilePath $candidate -Arguments $VersionArgs -TimeoutSeconds 15
            $combined = "$($stubCheck.output) $($stubCheck.error)"
            if ($combined -match 'was not found|Microsoft Store|App execution alias') {
                $stubsSkipped += $candidate
                continue
            }
        }

        $resolvedPath = $candidate
        break
    }

    # Several tools install correctly but never add themselves to PATH -
    # Blender's installer is the usual example, and adb lives inside Unity's
    # bundled Android SDK. PATH alone would report those as NOT_FOUND even
    # though winget just installed them successfully.
    if (-not $resolvedPath) {
        foreach ($pattern in $ExtraPaths) {
            $match = Get-Item -Path $pattern -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending | Select-Object -First 1
            if ($match) { $resolvedPath = $match.FullName; break }
        }
    }

    if (-not $resolvedPath) {
        $tried = "PATH: $($Commands -join ', ')"
        if ($ExtraPaths.Count -gt 0) { $tried += "`r`nPaths: $($ExtraPaths -join ', ')" }
        if ($stubsSkipped.Count -gt 0) {
            $tried += "`r`nSkipped Microsoft Store alias stub(s): $($stubsSkipped -join ', ')"
            $info.status = "STORE_ALIAS_STUB_ONLY"
            $info.notes += "Only a Microsoft Store app-execution-alias stub was on PATH; not a real install."
        }
        Save-Probe -Name $Name -Title "$Name (not found)" -Body $tried
        return [pscustomobject]$info
    }

    $info.installed = $true
    $info.path = $resolvedPath
    if ($stubsSkipped.Count -gt 0) {
        $info.notes += "Ignored Store alias stub(s) ahead of this on PATH: $($stubsSkipped -join ', ')"
    }

    $probeText = New-Object System.Text.StringBuilder
    [void]$probeText.AppendLine("resolved path: $($info.path)")
    [void]$probeText.AppendLine("")

    $versionResult = Invoke-Probe -FilePath $info.path -Arguments $VersionArgs
    [void]$probeText.AppendLine("### $($VersionArgs -join ' ')  (exit: $($versionResult.exitCode))")
    [void]$probeText.AppendLine($versionResult.output)
    if ($versionResult.error) { [void]$probeText.AppendLine("[stderr] $($versionResult.error)") }
    [void]$probeText.AppendLine("")

    if ($versionResult.ran -and $versionResult.output) {
        $firstLine = ($versionResult.output -split "\r?\n" | Where-Object { $_.Trim() } | Select-Object -First 1)
        if ($firstLine) { $info.version = $firstLine.Trim() }
    }

    $helpResult = Invoke-Probe -FilePath $info.path -Arguments $HelpArgs
    [void]$probeText.AppendLine("### $($HelpArgs -join ' ')  (exit: $($helpResult.exitCode))")
    [void]$probeText.AppendLine($helpResult.output)
    if ($helpResult.error) { [void]$probeText.AppendLine("[stderr] $($helpResult.error)") }
    [void]$probeText.AppendLine("")

    foreach ($label in $ExtraProbes.Keys) {
        $extraResult = Invoke-Probe -FilePath $info.path -Arguments $ExtraProbes[$label]
        [void]$probeText.AppendLine("### $label  (exit: $($extraResult.exitCode))")
        [void]$probeText.AppendLine($extraResult.output)
        if ($extraResult.error) { [void]$probeText.AppendLine("[stderr] $($extraResult.error)") }
        [void]$probeText.AppendLine("")
    }

    if ($versionResult.ran -or $helpResult.ran) { $info.status = "OK" }
    else { $info.status = "FOUND_BUT_NOT_RUNNABLE" }

    Save-Probe -Name $Name -Title "$Name capability probe" -Body $probeText.ToString()
    return [pscustomobject]$info
}

Write-Host "Surveying hardware..."

$os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$systemDrive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$($env:SystemDrive)'"

$gpus = @()
foreach ($video in (Get-CimInstance Win32_VideoController)) {
    # AdapterRAM is a uint32 and silently wraps for cards above 4 GB, so it is
    # recorded as a hint only - nvidia-smi below is the trustworthy source.
    $gpus += [ordered]@{
        name              = $video.Name
        driverVersion     = $video.DriverVersion
        adapterRamGbHint  = if ($video.AdapterRAM) { [Math]::Round($video.AdapterRAM / 1GB, 2) } else { $null }
    }
}

$nvidia = [ordered]@{ available = $false; raw = $null }
$nvidiaSmi = Get-Command "nvidia-smi" -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    $smiResult = Invoke-Probe -FilePath $nvidiaSmi.Source -Arguments @(
        "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader")
    if ($smiResult.ran -and $smiResult.exitCode -eq 0) {
        $nvidia.available = $true
        $nvidia.raw = $smiResult.output.Trim()
    }
    Save-Probe -Name "nvidia-smi" -Title "nvidia-smi GPU query" -Body ($smiResult.output + "`r`n[stderr] " + $smiResult.error)
}

$hardware = [ordered]@{
    os            = "$($os.Caption) $($os.Version)"
    osArchitecture = $os.OSArchitecture
    cpu           = if ($cpu) { $cpu.Name.Trim() } else { $null }
    cpuCores      = if ($cpu) { $cpu.NumberOfCores } else { $null }
    cpuThreads    = if ($cpu) { $cpu.NumberOfLogicalProcessors } else { $null }
    ramTotalGb    = [Math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
    ramFreeGb     = [Math]::Round($os.FreePhysicalMemory / 1MB, 2)
    systemDriveFreeGb = if ($systemDrive) { [Math]::Round($systemDrive.FreeSpace / 1GB, 2) } else { $null }
    gpus          = $gpus
    nvidiaSmi     = $nvidia
}

Write-Host "Probing CLI tools..."

$tools = [ordered]@{}

$tools.python = Get-ToolInfo -Name "python" -Commands @("python", "python3", "py") -VersionArgs @("--version") -HelpArgs @("--version")
$tools.git = Get-ToolInfo -Name "git" -Commands @("git")
$tools.node = Get-ToolInfo -Name "node" -Commands @("node")

# Section 2: Claude Code's non-interactive support must be verified, not
# assumed. The full --help text is what decides whether the orchestrator may
# call it as a subprocess at all.
$tools.claude = Get-ToolInfo -Name "claude" -Commands @("claude") -VersionArgs @("--version") -HelpArgs @("--help")

# Section 3: codex exec is the review entry point; its help decides which
# flags (json output, schema, output file) actually exist in this version.
$tools.codex = Get-ToolInfo -Name "codex" -Commands @("codex") -VersionArgs @("--version") -HelpArgs @("--help") `
    -ExtraProbes @{ "codex exec --help" = @("exec", "--help") }

$tools.ollama = Get-ToolInfo -Name "ollama" -Commands @("ollama") -VersionArgs @("--version") -HelpArgs @("--help") `
    -ExtraProbes @{ "ollama list" = @("list"); "ollama ps" = @("ps") }

$tools.blender = Get-ToolInfo -Name "blender" -Commands @("blender") -VersionArgs @("--version") -HelpArgs @("--help") `
    -ExtraPaths @(
        "C:\Program Files\Blender Foundation\Blender*\blender.exe",
        "$env:LOCALAPPDATA\Programs\Blender Foundation\Blender*\blender.exe"
    )

# adb ships inside Unity's bundled Android SDK rather than on PATH.
$tools.adb = Get-ToolInfo -Name "adb" -Commands @("adb") -VersionArgs @("version") -HelpArgs @("--version") `
    -ExtraPaths @(
        "C:\Program Files\Unity\Hub\Editor\*\Editor\Data\PlaybackEngines\AndroidPlayer\SDK\platform-tools\adb.exe",
        "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
    )

Write-Host "Probing Ollama HTTP API..."

# Section 4 wants the API checked, not just the binary: the CLI can exist
# while the server is down, and the orchestrator talks to the server.
$ollamaApi = [ordered]@{
    url          = $OllamaUrl
    reachable    = $false
    models       = @()
    loadedModels = @()
    error        = $null
    responseMs   = $null
}

try {
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $tags = Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -Method Get -TimeoutSec 10
    $stopwatch.Stop()

    $ollamaApi.reachable = $true
    $ollamaApi.responseMs = $stopwatch.ElapsedMilliseconds
    if ($tags.models) {
        $ollamaApi.models = @($tags.models | ForEach-Object {
            [ordered]@{
                name          = $_.name
                sizeGb        = if ($_.size) { [Math]::Round($_.size / 1GB, 2) } else { $null }
                parameterSize = $_.details.parameter_size
                quantization  = $_.details.quantization_level
                family        = $_.details.family
            }
        })
    }
}
catch {
    $ollamaApi.error = $_.Exception.Message
}

if ($ollamaApi.reachable) {
    try {
        $running = Invoke-RestMethod -Uri "$OllamaUrl/api/ps" -Method Get -TimeoutSec 10
        if ($running.models) { $ollamaApi.loadedModels = @($running.models | ForEach-Object { $_.name }) }
    }
    catch { }
}

Write-Host "Locating Unity / Android SDK / JDK..."

$unityEditors = @()
$hubRoot = "C:\Program Files\Unity\Hub\Editor"
if (Test-Path $hubRoot) {
    foreach ($editorDir in (Get-ChildItem -Path $hubRoot -Directory -ErrorAction SilentlyContinue)) {
        $exe = Join-Path $editorDir.FullName "Editor\Unity.exe"
        if (Test-Path $exe) {
            $unityEditors += [ordered]@{ version = $editorDir.Name; path = $exe }
        }
    }
}

$requiredUnityVersion = $null
$projectVersionFile = Join-Path $RepoPath "ProjectSettings\ProjectVersion.txt"
if (Test-Path $projectVersionFile) {
    $versionLine = Get-Content $projectVersionFile | Where-Object { $_ -match '^m_EditorVersion:' } | Select-Object -First 1
    if ($versionLine) { $requiredUnityVersion = ($versionLine -replace '^m_EditorVersion:\s*', '').Trim() }
}

$matchingUnity = $unityEditors | Where-Object { $_.version -eq $requiredUnityVersion } | Select-Object -First 1

$unity = [ordered]@{
    requiredByProject = $requiredUnityVersion
    installedEditors  = $unityEditors
    matchingEditorPath = if ($matchingUnity) { $matchingUnity.path } else { $null }
    status = if ($matchingUnity) { "OK" } elseif ($unityEditors.Count -gt 0) { "VERSION_MISMATCH" } else { "NOT_FOUND" }
}

$androidSdkPath = $env:ANDROID_HOME
if (-not $androidSdkPath) { $androidSdkPath = $env:ANDROID_SDK_ROOT }
if ((-not $androidSdkPath) -and $matchingUnity) {
    $bundled = Join-Path (Split-Path (Split-Path $matchingUnity.path -Parent) -Parent) "Editor\Data\PlaybackEngines\AndroidPlayer\SDK"
    if (Test-Path $bundled) { $androidSdkPath = $bundled }
}

$jdkPath = $env:JAVA_HOME
if ((-not $jdkPath) -and $matchingUnity) {
    $bundledJdk = Join-Path (Split-Path (Split-Path $matchingUnity.path -Parent) -Parent) "Editor\Data\PlaybackEngines\AndroidPlayer\OpenJDK"
    if (Test-Path $bundledJdk) { $jdkPath = $bundledJdk }
}

$android = [ordered]@{
    sdkPath   = $androidSdkPath
    sdkExists = [bool]($androidSdkPath -and (Test-Path $androidSdkPath))
    jdkPath   = $jdkPath
    jdkExists = [bool]($jdkPath -and (Test-Path $jdkPath))
}

# Section 7: the orchestrator must know a paid key EXISTS precisely so it can
# refuse to use it. Only presence is recorded - never the value.
$paidKeyNames = @("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "REPLICATE_API_TOKEN", "FAL_KEY", "STABILITY_API_KEY")
$paidKeysPresent = [ordered]@{}
foreach ($keyName in $paidKeyNames) {
    $paidKeysPresent[$keyName] = [bool]([Environment]::GetEnvironmentVariable($keyName))
}

$machineProfile = [ordered]@{
    generatedAt        = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    generatedBy        = "AI_GAME_COMPANY/tools/detect-environment.ps1"
    repoPath           = $RepoPath
    machineName        = $env:COMPUTERNAME
    hardware           = $hardware
    tools              = $tools
    ollamaApi          = $ollamaApi
    unity              = $unity
    android            = $android
    paidApiKeysPresent = $paidKeysPresent
    note               = "Raw CLI help text is in cli-probes/. Per master prompt 41 STEP 5, adapters must only use commands that appear there."
}

$json = $machineProfile | ConvertTo-Json -Depth 8
Set-Content -Path $profilePath -Value $json -Encoding UTF8

Write-Host ""
Write-Host "=== SUMMARY ==="
Write-Host "CPU     : $($hardware.cpu) ($($hardware.cpuCores)C/$($hardware.cpuThreads)T)"
Write-Host "RAM     : $($hardware.ramTotalGb) GB total, $($hardware.ramFreeGb) GB free"
Write-Host "GPU     : $(if ($nvidia.available) { $nvidia.raw } else { ($gpus | ForEach-Object { $_.name }) -join '; ' })"
foreach ($toolName in $tools.Keys) {
    $tool = $tools[$toolName]
    Write-Host ("{0,-8}: {1}" -f $toolName, $(if ($tool.installed) { "$($tool.status) - $($tool.version)" } else { "NOT FOUND" }))
}
Write-Host "Ollama  : $(if ($ollamaApi.reachable) { "API OK, $($ollamaApi.models.Count) model(s)" } else { "API unreachable - $($ollamaApi.error)" })"
Write-Host "Unity   : $($unity.status) (project needs $($unity.requiredByProject))"
Write-Host ""
Write-Host "Profile : $profilePath"
Write-Host "Probes  : $probeDir"

if (-not $Commit) {
    Write-Host ""
    Write-Host "(Pass -Commit to push this to the fork so Claude Code can read it.)"
    exit 0
}

Invoke-Git @("add", "--", $configRelative) | Out-Null

$pending = Invoke-Git @("status", "--porcelain", "--", $configRelative)
if (-not $pending) {
    Write-Host "Nothing changed since the last survey; nothing committed."
    exit 0
}

Invoke-Git @("commit", "-m", "chore: update AI_GAME_COMPANY hardware/CLI profile") | Out-Null

if ($NoPush) {
    Write-Host "Committed; the caller will push."
    exit 0
}

Invoke-Git @("push", $OriginRemote, $Branch) -Retries 4 | Out-Null
Write-Host "Pushed. Claude Code can read the profile now."
exit 0
