# Model download checklist (RTX 5070 / 12GB)

## One-command download

```powershell
cd C:\Users\user\Documents\DirectorX
powershell -ExecutionPolicy Bypass -File .\scripts\download_flux.ps1
```

This pulls:
- `flux1-dev-fp8.safetensors` → `C:\ComfyUI\models\checkpoints\` (~17.2GB)
- Wan 2.2 LightX2V 4-step LoRAs → `C:\ComfyUI\models\loras\`

You already have Wan 2.2 I2V FP8 + VAE + UMT5 encoder.

## After download

```powershell
# Rebuild API graphs + NODE_MAP (already done once; re-run if you edit graphs)
python scripts\build_workflow_api.py

# Start ComfyUI, then:
python main.py
```

## Architecture (TWO_STAGE=True in config.py)

1. **Flux FP8** generates a cinematic still  
2. **Wan 2.2 I2V** animates that still  
3. DirectorX stitches clips + voice + captions

## Disk estimate

~20GB additional for Flux FP8 + LoRAs. Keep ≥25GB free before downloading.
