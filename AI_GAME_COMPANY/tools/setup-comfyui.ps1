<#
.SYNOPSIS
  Installs ComfyUI with the SD 1.5 + IP-Adapter stack and a ready 도리 workflow.

.DESCRIPTION
  ComfyUI is the interactive half. generate-sprite.py is the scripted half:
  same model, same IP-Adapter, no UI, callable from the orchestrator. Use
  ComfyUI to find settings by hand and generate-sprite.py to repeat them in
  bulk once they are found.

  WHAT COMFYUI DOES NOT CHANGE. It is a graph runner, not a memory
  compressor. Qwen-Image is still out of reach on this machine - about 18.5 GB
  of working set against 15.71 GB of total RAM with no dedicated VRAM. That is
  arithmetic, checked by HardwareProfile.image_model_fit('qwen-image'), and
  installing ComfyUI does not move it. What ComfyUI IS good for here is
  SD 1.5 + IP-Adapter, which fits.

  Licences, all verified before install and recorded in LICENSE_REGISTRY.json:
    ComfyUI            GPL-3.0     build-time tool, never bundled in the APK
    SD 1.5             OpenRAIL-M  commercial use permitted
    IP-Adapter         Apache-2.0
    ComfyUI_IPAdapter_plus  MIT    the custom node that exposes it

  ASCII only - PowerShell 5.1 reads a BOM-less UTF-8 .ps1 in the local
  codepage, which mangles non-ASCII string literals.

.PARAMETER InstallPath
  Where ComfyUI goes. Defaults to C:\ComfyUI - deliberately OUTSIDE the game
  repository, because it is a multi-GB tool checkout, not project source.

.PARAMETER RepoPath
  The game repository, for the workflow file and the reference image.

.PARAMETER SkipModels
  Install ComfyUI and the node but download no weights (about 6 GB).

.EXAMPLE
  .\AI_GAME_COMPANY\tools\setup-comfyui.ps1
#>

[CmdletBinding()]
param(
    [string]$InstallPath = "C:\ComfyUI",
    [string]$RepoPath = "C:\Dory_tycoon",
    [switch]$SkipModels
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$message) {
    Write-Host ""
    Write-Host "=== $message ===" -ForegroundColor Cyan
}

function Get-RealPython {
    foreach ($candidate in @("python", "python3", "py")) {
        $found = Get-Command $candidate -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $found) { continue }
        # A Microsoft Store alias stub exists on PATH, runs, and only prints
        # "Python was not found" - the trap that made the installer report
        # Python as already present.
        if ($found.Source -like "*\WindowsApps\*") {
            $probe = & $found.Source --version 2>&1 | Out-String
            if ($probe -match "was not found|Microsoft Store") { continue }
        }
        return $found.Source
    }
    return $null
}

$python = Get-RealPython
if (-not $python) {
    Write-Host "ERROR: no real Python found." -ForegroundColor Red
    Write-Host "  Run .\AI_GAME_COMPANY\tools\install-missing-tools.ps1 -Commit first."
    exit 2
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: git not found on PATH." -ForegroundColor Red
    exit 2
}

Write-Host "Python : $python"
Write-Host "ComfyUI: $InstallPath"

Write-Step "ComfyUI"
if (Test-Path (Join-Path $InstallPath ".git")) {
    Write-Host "Already cloned; pulling."
    git -C $InstallPath pull --ff-only
} else {
    git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git $InstallPath
}

& $python -m pip install --quiet -r (Join-Path $InstallPath "requirements.txt")

Write-Step "IP-Adapter node"
$nodeDir = Join-Path $InstallPath "custom_nodes\ComfyUI_IPAdapter_plus"
if (Test-Path (Join-Path $nodeDir ".git")) {
    git -C $nodeDir pull --ff-only
} else {
    git clone --depth 1 https://github.com/cubiq/ComfyUI_IPAdapter_plus.git $nodeDir
}

if ($SkipModels) {
    Write-Host ""
    Write-Host "Skipping model downloads as requested."
} else {
    Write-Step "Models (about 6 GB, first run only)"

    # Downloaded with huggingface_hub rather than raw URLs: it resolves the
    # real file locations, resumes, and caches, so a dropped connection does
    # not restart 4 GB from zero.
    & $python -m pip install --quiet huggingface_hub

    $checkpoints = Join-Path $InstallPath "models\checkpoints"
    $ipadapter   = Join-Path $InstallPath "models\ipadapter"
    $clipvision  = Join-Path $InstallPath "models\clip_vision"
    foreach ($dir in @($checkpoints, $ipadapter, $clipvision)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    $downloader = @"
import sys
from huggingface_hub import hf_hub_download
import shutil, pathlib

jobs = [
    ("stable-diffusion-v1-5/stable-diffusion-v1-5", "v1-5-pruned-emaonly.safetensors", None, sys.argv[1]),
    ("h94/IP-Adapter", "ip-adapter-plus_sd15.bin", "models", sys.argv[2]),
    ("h94/IP-Adapter", "model.safetensors", "models/image_encoder", sys.argv[3]),
]

for repo, filename, subfolder, dest_dir in jobs:
    print(f"-> {repo}/{subfolder or ''}/{filename}")
    src = hf_hub_download(repo_id=repo, filename=filename, subfolder=subfolder)
    dest = pathlib.Path(dest_dir) / pathlib.Path(filename).name
    if not dest.exists():
        shutil.copy2(src, dest)
    print(f"   {dest}")
"@
    $downloaderPath = Join-Path $env:TEMP "ccr-comfy-download.py"
    Set-Content -Path $downloaderPath -Value $downloader -Encoding ASCII
    & $python $downloaderPath $checkpoints $ipadapter $clipvision
    Remove-Item $downloaderPath -ErrorAction SilentlyContinue
}

Write-Step "Workflow and reference"
$workflowSrc = Join-Path $RepoPath "AI_GAME_COMPANY\comfyui\dori-ipadapter.json"
$inputDir = Join-Path $InstallPath "input"
New-Item -ItemType Directory -Path $inputDir -Force | Out-Null

$reference = Join-Path $RepoPath "Assets\Common\Art\Runner\player.png"
if (Test-Path $reference) {
    Copy-Item $reference (Join-Path $inputDir "dori_reference.png") -Force
    Write-Host "Reference copied to $inputDir\dori_reference.png"
} else {
    Write-Host "WARNING: $reference not found - load a reference by hand." -ForegroundColor Yellow
}

if (Test-Path $workflowSrc) {
    Write-Host "Workflow: $workflowSrc"
    Write-Host "  In ComfyUI use Workflow > Open and pick that file."
} else {
    Write-Host "WARNING: workflow file missing at $workflowSrc" -ForegroundColor Yellow
}

Write-Step "Done"
Write-Host "Start ComfyUI:"
Write-Host "  cd $InstallPath"
Write-Host "  $python main.py --cpu"
Write-Host ""
Write-Host "--cpu is not optional here: there is no dedicated VRAM, and without"
Write-Host "it ComfyUI tries the integrated GPU and fails on allocation."
Write-Host "Then open http://127.0.0.1:8188 in a browser."
Write-Host ""
Write-Host "Expect minutes per image. The dial that matters is the IPAdapter"
Write-Host "node's weight: high keeps Dori but resists the new pose, low frees"
Write-Host "the pose and drifts off-character. Sweep it."
Write-Host ""
Write-Host "For bulk generation once settings are found, use the scripted path"
Write-Host "instead - same model, same adapter, no clicking:"
Write-Host "  $python AI_GAME_COMPANY\tools\generate-sprite.py txt2img \"
Write-Host "      --ip-image Assets\Common\Art\Runner\player.png --ip-scale 0.7 \"
Write-Host "      --pose \"side view, facing right, running\" --count 4 \"
Write-Host "      --out AI_GAME_COMPANY\generated\dori\run.png"
exit 0
