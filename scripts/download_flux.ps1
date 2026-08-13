# Download DirectorX cinematic models (RTX 5070 / 12GB) - Option C
# Flux.1-dev FP8 (primary) + GGUF Q6 (fallback). SHA-256 gate. Never silent-accept corrupt files.
# Requires: hf CLI (pip install -U "huggingface_hub[cli]") OR curl + HF token
$ErrorActionPreference = "Stop"
$Comfy = "C:\ComfyUI"

# Official Comfy-Org flux1-dev-fp8.safetensors
$FluxFp8Name = "flux1-dev-fp8.safetensors"
$FluxFp8Sha  = "8e91b68084b53a7fc44ed2a3756d821e355ac1a7b6fe29be760c1db532f3d88a"

# City96-style GGUF (ComfyUI-GGUF / UnetLoaderGGUF). Adjust filename if your pack differs.
$FluxGgufName = "flux1-dev-Q6_K.gguf"
$FluxGgufRepo = "city96/FLUX.1-dev-gguf"

function Ensure-Dir($p) {
  if (-not (Test-Path $p)) { New-Item -ItemType Directory -Force -Path $p | Out-Null }
}

function Get-Sha256([string]$Path) {
  return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
}

function Assert-FluxFp8([string]$Path) {
  if (-not (Test-Path $Path)) { return $false }
  $len = (Get-Item $Path).Length
  if ($len -lt 15GB) {
    Write-Warning "Flux FP8 too small ($len bytes) - treating as corrupt"
    return $false
  }
  Write-Host "    Computing SHA256 (this takes a few minutes)..."
  $hash = Get-Sha256 $Path
  if ($hash -ne $FluxFp8Sha) {
    Write-Warning "SHA mismatch! got=$hash expected=$FluxFp8Sha"
    return $false
  }
  Write-Host "    SHA256 OK"
  return $true
}

Ensure-Dir "$Comfy\models\checkpoints"
Ensure-Dir "$Comfy\models\unet"
Ensure-Dir "$Comfy\models\loras"
Ensure-Dir "$Comfy\models\text_encoders"
Ensure-Dir "$Comfy\models\vae"
Ensure-Dir "$Comfy\models\diffusion_models"

Write-Host "==> Free space check"
$freeGB = [math]::Round((Get-PSDrive C).Free / 1GB, 1)
Write-Host "    C: free = $freeGB GB"
if ($freeGB -lt 25) {
  Write-Warning "Low disk space. Need ~25GB+ for Flux FP8 + GGUF."
}

# --- 1) Flux Dev FP8 ---
$flux = Join-Path $Comfy "models\checkpoints\$FluxFp8Name"
if (Assert-FluxFp8 $flux) {
  Write-Host "[=] Flux FP8 verified present"
} else {
  if (Test-Path $flux) {
    Write-Host "[!] Removing corrupt/incomplete Flux FP8"
    Remove-Item $flux -Force
  }
  Write-Host "[+] Downloading Flux.1 Dev FP8 (~17.2GB) to checkpoints"
  hf download Comfy-Org/flux1-dev $FluxFp8Name --local-dir (Join-Path $Comfy "models\checkpoints")
  if (-not (Assert-FluxFp8 $flux)) {
    throw "Flux FP8 failed SHA verification after download. Aborting - will not use SD1.5."
  }
}

# --- 2) Flux GGUF Q6 fallback (Option C) ---
$gguf = Join-Path $Comfy "models\unet\$FluxGgufName"
if (Test-Path $gguf -and ((Get-Item $gguf).Length -gt 8GB)) {
  $gb = [math]::Round((Get-Item $gguf).Length / 1GB, 2)
  Write-Host "[=] Flux GGUF present: $FluxGgufName ($gb GB)"
} else {
  Write-Host "[+] Downloading Flux GGUF fallback $FluxGgufName to unet"
  try {
    hf download $FluxGgufRepo $FluxGgufName --local-dir (Join-Path $Comfy "models\unet")
  } catch {
    Write-Warning "GGUF download failed: $_. Install ComfyUI-GGUF later if FP8 works alone."
  }
}

Write-Host ""
Write-Host "Done (Option C assets). Next:"
Write-Host "  1. python scripts\verify_flux_checkpoint.py"
Write-Host "  2. python scripts\build_workflow_api.py"
Write-Host "  3. Restart ComfyUI --lowvram"
Write-Host "  4. Smoke still, then python main.py"
