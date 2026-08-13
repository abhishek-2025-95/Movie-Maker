# Download RTX 5070 / 12GB GGUF profile for DirectorX
# Flux.1-dev Q5_K_S (city96; Q5_K_M not published) + Wan 2.2 I2V Q4_K_M MoE pair
# + Flux text encoders (T5 FP8 + CLIP-L) + AE VAE
$ErrorActionPreference = "Stop"
$Comfy = "C:\ComfyUI"

function Ensure-Dir($p) {
  if (-not (Test-Path $p)) { New-Item -ItemType Directory -Force -Path $p | Out-Null }
}

function Have-File([string]$Path, [double]$MinGB) {
  if (-not (Test-Path $Path)) { return $false }
  $gb = (Get-Item $Path).Length / 1GB
  return ($gb -ge $MinGB)
}

Ensure-Dir "$Comfy\models\unet"
Ensure-Dir "$Comfy\models\text_encoders"
Ensure-Dir "$Comfy\models\clip"
Ensure-Dir "$Comfy\models\vae"
Ensure-Dir "$Comfy\models\diffusion_models"

$freeGB = [math]::Round((Get-PSDrive C).Free / 1GB, 1)
Write-Host "==> C: free = $freeGB GB"
if ($freeGB -lt 40) {
  Write-Warning "Need ~40GB+ free for GGUF profile. Free disk then re-run."
}

# Flux UNET GGUF
$FluxGguf = "flux1-dev-Q5_K_S.gguf"
$FluxGgufPath = Join-Path $Comfy "models\unet\$FluxGguf"
if (Have-File $FluxGgufPath 7.5) {
  Write-Host "[=] Flux GGUF present: $FluxGguf"
} else {
  Write-Host "[+] Downloading $FluxGguf from city96/FLUX.1-dev-gguf"
  hf download city96/FLUX.1-dev-gguf $FluxGguf --local-dir (Join-Path $Comfy "models\unet")
}

# Wan 2.2 I2V MoE GGUF Q4_K_M
$WanHigh = "wan2.2_i2v_high_noise_14B_Q4_K_M.gguf"
$WanLow  = "wan2.2_i2v_low_noise_14B_Q4_K_M.gguf"
$WanRepo = "bullerwins/Wan2.2-I2V-A14B-GGUF"
foreach ($name in @($WanHigh, $WanLow)) {
  $p = Join-Path $Comfy "models\unet\$name"
  if (Have-File $p 8.5) {
    Write-Host "[=] Wan GGUF present: $name"
  } else {
    Write-Host "[+] Downloading $name from $WanRepo"
    hf download $WanRepo $name --local-dir (Join-Path $Comfy "models\unet")
  }
}

# Flux text encoders
$T5 = "t5xxl_fp8_e4m3fn.safetensors"
$ClipL = "clip_l.safetensors"
$TeDir = Join-Path $Comfy "models\text_encoders"
$ClipDir = Join-Path $Comfy "models\clip"
if (Have-File (Join-Path $TeDir $T5) 4.0) {
  Write-Host "[=] T5 FP8 present: $T5"
} else {
  Write-Host "[+] Downloading $T5"
  hf download comfyanonymous/flux_text_encoders $T5 --local-dir $TeDir
}
if ((Have-File (Join-Path $TeDir $ClipL) 0.2) -or (Have-File (Join-Path $ClipDir $ClipL) 0.2)) {
  Write-Host "[=] CLIP-L present: $ClipL"
} else {
  Write-Host "[+] Downloading $ClipL"
  hf download comfyanonymous/flux_text_encoders $ClipL --local-dir $TeDir
  Copy-Item (Join-Path $TeDir $ClipL) (Join-Path $ClipDir $ClipL) -Force -ErrorAction SilentlyContinue
}

# Flux AE VAE (BFL gated - may need huggingface-cli login)
$Ae = "ae.safetensors"
$AePath = Join-Path $Comfy "models\vae\$Ae"
if (Have-File $AePath 0.2) {
  Write-Host "[=] Flux AE VAE present"
} else {
  Write-Host "[+] Downloading ae.safetensors from black-forest-labs/FLUX.1-dev"
  try {
    hf download black-forest-labs/FLUX.1-dev $Ae --local-dir (Join-Path $Comfy "models\vae")
  } catch {
    Write-Warning "AE download failed (gated?). Run: huggingface-cli login then re-run this script."
    Write-Warning "Until AE exists, DirectorX keeps Flux FP8 stills + Wan GGUF motion."
  }
}

Write-Host ""
Write-Host "Done. Next:"
Write-Host "  python scripts\build_workflow_api.py"
Write-Host "  python -c `"import config; config.refresh_workflow_paths(); print(config.WORKFLOW_FLUX); print(config.WORKFLOW_WAN)`""
