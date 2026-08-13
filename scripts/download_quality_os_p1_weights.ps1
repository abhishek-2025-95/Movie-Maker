# Quality OS P1 — download Real-ESRGAN + Flux IP-Adapter (XLabs) + CLIP Vision
$ErrorActionPreference = "Stop"
$Comfy = "C:\ComfyUI"

function Ensure-Dir($p) {
  if (-not (Test-Path $p)) { New-Item -ItemType Directory -Force -Path $p | Out-Null }
}

function Have-File([string]$Path, [double]$MinMB) {
  if (-not (Test-Path $Path)) { return $false }
  $mb = (Get-Item $Path).Length / 1MB
  return ($mb -ge $MinMB)
}

Ensure-Dir "$Comfy\models\upscale_models"
Ensure-Dir "$Comfy\models\xlabs\ipadapters"
Ensure-Dir "$Comfy\models\clip_vision"
Ensure-Dir "$Comfy\custom_nodes"

$freeGB = [math]::Round((Get-PSDrive C).Free / 1GB, 1)
Write-Host "==> C: free = $freeGB GB"

# Custom node: XLabs Flux IP-Adapter
$XFlux = Join-Path $Comfy "custom_nodes\x-flux-comfyui"
if (-not (Test-Path (Join-Path $XFlux "nodes.py"))) {
  Write-Host "[+] Cloning XLabs-AI/x-flux-comfyui"
  git clone --depth 1 https://github.com/XLabs-AI/x-flux-comfyui.git $XFlux
} else {
  Write-Host "[=] x-flux-comfyui present"
}

# RealESRGAN x2plus (~64MB) — download to TEMP then copy (avoids file locks)
$Esr = Join-Path $Comfy "models\upscale_models\RealESRGAN_x2plus.pth"
if (Have-File $Esr 50) {
  Write-Host "[=] RealESRGAN_x2plus.pth present"
} else {
  Write-Host "[+] Downloading RealESRGAN_x2plus.pth (GitHub release via TEMP)"
  $tmpEsr = Join-Path $env:TEMP "RealESRGAN_x2plus.pth"
  curl.exe -L --retry 5 --retry-delay 2 -o $tmpEsr "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth"
  if (-not (Have-File $tmpEsr 50)) { throw "RealESRGAN download incomplete: $tmpEsr" }
  Copy-Item $tmpEsr $Esr -Force
}

# Flux IP-Adapter v2 weights
$Ipa = Join-Path $Comfy "models\xlabs\ipadapters\ip_adapter.safetensors"
if (Have-File $Ipa 400) {
  Write-Host "[=] ip_adapter.safetensors present"
} else {
  Write-Host "[+] Downloading XLabs flux-ip-adapter-v2 ip_adapter.safetensors"
  hf download XLabs-AI/flux-ip-adapter-v2 ip_adapter.safetensors --local-dir (Join-Path $Comfy "models\xlabs\ipadapters")
}

# CLIP ViT-L for XLabs Flux IP-Adapter
$Clip = Join-Path $Comfy "models\clip_vision\clip-vit-large-patch14.safetensors"
if (Have-File $Clip 300) {
  Write-Host "[=] clip-vit-large-patch14.safetensors present"
} else {
  Write-Host "[+] Downloading OpenAI CLIP ViT-L -> clip-vit-large-patch14.safetensors"
  $tmp = Join-Path $env:TEMP "dx_clip_vit_l"
  Ensure-Dir $tmp
  hf download openai/clip-vit-large-patch14 model.safetensors --local-dir $tmp
  Copy-Item (Join-Path $tmp "model.safetensors") $Clip -Force
}

# spandrel for Real-ESRGAN inference inside DirectorX venv
Write-Host "[+] Ensuring spandrel in DirectorX .venv"
& "C:\Users\user\Documents\DirectorX\.venv\Scripts\python.exe" -m pip install -q "spandrel>=0.3.0"

Write-Host ""
Write-Host "==> P1 download pass complete. Restart ComfyUI before IP-Adapter smoke."
Write-Host "    Verify: .\.venv\Scripts\python.exe -c `"from quality_os.preflight import check_p1; r=check_p1(); print(r)`""
