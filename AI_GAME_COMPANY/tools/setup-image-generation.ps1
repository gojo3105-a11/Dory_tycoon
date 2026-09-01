<#
.SYNOPSIS
  Installs the local, free image generation stack and runs a first generation.

.DESCRIPTION
  Free and local: Stable Diffusion v1.5 through diffusers, on the CPU. No API,
  no account, no cost, no cloud call.

  WHY THIS RUNS HERE AND NOT IN THE CLAUDE CONTAINER. The tooling was written
  and licence-checked in the container, but huggingface.co is blocked there by
  the organization's egress policy (the agent proxy answers 403 to CONNECT), so
  the model weights cannot be downloaded. Routing around an egress denial is
  explicitly forbidden. This PC has ordinary internet, so generation happens
  here instead.

  Section 43 permits installing free components. Section 9's requirement to
  read the exact repository licence BEFORE installing was satisfied first:
  stable-diffusion-v1-5 is APPROVED in config/LICENSE_REGISTRY.json under
  CreativeML OpenRAIL-M, which permits commercial use. The faster Turbo
  variants were rejected because their licence is non-commercial.

  ASCII only - Windows PowerShell 5.1 reads a BOM-less UTF-8 .ps1 in the local
  codepage, which mangles non-ASCII string literals.

.PARAMETER RepoPath
  The repository clone. Defaults to C:\Dory_tycoon.

.PARAMETER SkipInstall
  Skip pip install and go straight to generating.

.PARAMETER SkipGenerate
  Install only.

.EXAMPLE
  .\AI_GAME_COMPANY\tools\setup-image-generation.ps1
#>

[CmdletBinding()]
param(
    [string]$RepoPath = "C:\Dory_tycoon",
    [switch]$SkipInstall,
    [switch]$SkipGenerate
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$message) {
    Write-Host ""
    Write-Host "=== $message ===" -ForegroundColor Cyan
}

if (-not (Test-Path $RepoPath)) {
    Write-Host "ERROR: $RepoPath not found." -ForegroundColor Red
    exit 2
}

Set-Location $RepoPath

# Prefer a real Python over a Microsoft Store alias stub, which exists on PATH,
# runs, and only prints "Python was not found".
$python = $null
foreach ($candidate in @("python", "python3", "py")) {
    $found = Get-Command $candidate -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $found) { continue }
    if ($found.Source -like "*\WindowsApps\*") {
        $probe = & $found.Source --version 2>&1 | Out-String
        if ($probe -match "was not found|Microsoft Store") { continue }
    }
    $python = $found.Source
    break
}

if (-not $python) {
    Write-Host "ERROR: no real Python found." -ForegroundColor Red
    Write-Host "  Run .\AI_GAME_COMPANY\tools\install-missing-tools.ps1 -Commit first."
    exit 2
}

Write-Host "Python: $python"
& $python --version

if (-not $SkipInstall) {
    Write-Step "Installing (free, local, CPU only)"

    # The CPU wheel, explicitly. The default PyPI wheel bundles CUDA and is
    # about 2 GB larger for no benefit on a machine with no NVIDIA GPU.
    Write-Host "torch (CPU build) - this is the big one, several minutes..."
    & $python -m pip install --quiet torch torchvision --index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE -ne 0) {
        Write-Host "CPU index failed; falling back to the default PyPI wheel (larger)." -ForegroundColor Yellow
        & $python -m pip install --quiet torch torchvision
    }

    Write-Host "diffusers, transformers, accelerate, safetensors, pillow ..."
    & $python -m pip install --quiet diffusers transformers accelerate safetensors pillow

    Write-Host "rembg (background removal, for turning generations into sprites) ..."
    & $python -m pip install --quiet "rembg[cpu]" onnxruntime numpy

    & $python -c "import torch, diffusers; print('torch', torch.__version__); print('diffusers', diffusers.__version__); print('threads', torch.get_num_threads())"
}

if ($SkipGenerate) {
    Write-Host ""
    Write-Host "Install done. Skipping generation as requested."
    exit 0
}

Write-Step "First generation"
Write-Host "The model downloads on first run (about 4 GB) and is cached."
Write-Host "On a CPU each 512px image takes minutes, not seconds."
Write-Host ""

$outDir = Join-Path $RepoPath "AI_GAME_COMPANY\generated\dori"
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

# Which approach works is an empirical question, not one to guess at, so this
# generates all of them and lets the pictures decide.
$reference = "Assets\Common\Art\Runner\player.png"
$runPose = "side view profile, facing right, running, legs mid-stride"

# IP-Adapter first and with three scales, because ip-scale is the one dial
# that decides this: too high and the model refuses to leave the front-facing
# reference pose, too low and it stops being Dori. Sweeping beats guessing.
# img2img and plain txt2img are kept as controls - if IP-Adapter wins, that is
# worth seeing against something.
$runs = @(
    @{
        name = "ip-scale050"
        args = @("txt2img", "--ip-image", $reference, "--ip-scale", "0.50",
                 "--pose", $runPose, "--count", "2",
                 "--out", (Join-Path $outDir "ip-050.png"))
    },
    @{
        name = "ip-scale070"
        args = @("txt2img", "--ip-image", $reference, "--ip-scale", "0.70",
                 "--pose", $runPose, "--count", "2",
                 "--out", (Join-Path $outDir "ip-070.png"))
    },
    @{
        name = "ip-scale085"
        args = @("txt2img", "--ip-image", $reference, "--ip-scale", "0.85",
                 "--pose", $runPose, "--count", "2",
                 "--out", (Join-Path $outDir "ip-085.png"))
    },
    @{
        name = "i2i-control"
        args = @("img2img", "--init", $reference,
                 "--pose", $runPose, "--strength", "0.65", "--count", "2",
                 "--out", (Join-Path $outDir "i2i-065.png"))
    },
    @{
        name = "t2i-control"
        args = @("txt2img", "--pose", $runPose, "--count", "2",
                 "--out", (Join-Path $outDir "t2i.png"))
    }
)

foreach ($run in $runs) {
    Write-Step $run.name
    $started = Get-Date
    & $python "AI_GAME_COMPANY\tools\generate-sprite.py" @($run.args)
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $($run.name) exited $LASTEXITCODE" -ForegroundColor Red
        continue
    }
    $elapsed = [Math]::Round(((Get-Date) - $started).TotalMinutes, 1)
    Write-Host "$($run.name): ${elapsed} min" -ForegroundColor Green
}

Write-Step "Done"
Write-Host "Output: $outDir"
Write-Host ""
Write-Host "These are RAW images on a plain background, not sprites yet."
Write-Host "Look at them and pick the ones worth keeping. Section 30: whether a"
Write-Host "generation is any good is a human call, not the tool's."
Write-Host ""
Write-Host "To turn a keeper into a game sprite:"
Write-Host "  $python AI_GAME_COMPANY\tools\cutout-character.py \"
Write-Host "      --source $outDir\<chosen>.png \"
Write-Host "      --target Assets\Common\Art\Runner\player.png"
Write-Host ""
Write-Host "Then commit and push so Claude Code can see the result."
exit 0
