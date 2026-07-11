# Download DirectorX models for RTX 5070 (12GB)
# Requires: hf CLI (pip install -U huggingface_hub)
$ErrorActionPreference = "Stop"
$Comfy = "C:\ComfyUI"

function Ensure-Dir($p) {
  if (-not (Test-Path $p)) { New-Item -ItemType Directory -Force -Path $p | Out-Null }
}

Ensure-Dir "$Comfy\models\checkpoints"
Ensure-Dir "$Comfy\models\loras"
Ensure-Dir "$Comfy\models\text_encoders"
Ensure-Dir "$Comfy\models\vae"
Ensure-Dir "$Comfy\models\diffusion_models"

Write-Host "==> Free space check"
$freeGB = [math]::Round((Get-PSDrive C).Free / 1GB, 1)
Write-Host "    C: free = $freeGB GB"
if ($freeGB -lt 20) {
  Write-Warning "Low disk space. Flux FP8 is ~17GB. Free more space if download fails."
}

# 1) Flux Dev FP8 all-in-one (best simple path for quality on 12GB with offload)
$flux = "$Comfy\models\checkpoints\flux1-dev-fp8.safetensors"
if (Test-Path $flux) {
  Write-Host "[=] Flux FP8 already present"
} else {
  Write-Host "[+] Downloading Flux.1 Dev FP8 (~17.2GB) → checkpoints\"
  hf download Comfy-Org/flux1-dev flux1-dev-fp8.safetensors --local-dir "$Comfy\models\checkpoints"
}

# 2) Wan 2.2 LightX2V 4-step LoRAs (huge speed win on 5070)
$loras = @(
  "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors",
  "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"
)
foreach ($name in $loras) {
  $dest = "$Comfy\models\loras\$name"
  if (Test-Path $dest) {
    Write-Host "[=] LoRA present: $name"
  } else {
    Write-Host "[+] Downloading LoRA $name"
    hf download Comfy-Org/Wan_2.2_ComfyUI_Repackaged "split_files/loras/$name" --local-dir "$Comfy\models\loras\_tmp_wan"
    $found = Get-ChildItem "$Comfy\models\loras\_tmp_wan" -Recurse -Filter $name | Select-Object -First 1
    if ($found) {
      Move-Item $found.FullName $dest -Force
    }
  }
}

Write-Host ""
Write-Host "Done. Next:"
Write-Host "  1. Restart ComfyUI"
Write-Host "  2. python scripts\build_workflow_api.py"
Write-Host "  3. python main.py"
