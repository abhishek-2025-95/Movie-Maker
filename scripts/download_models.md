# Model download checklist (RTX 5070 / 12GB)

You already have Wan 2.2 I2V FP8 + Wan VAE in `C:\ComfyUI\models`.

## Required for best stills (Flux)

Place under ComfyUI model folders (exact filenames may vary by pack):

| Model | Typical folder | Notes |
|-------|----------------|-------|
| Flux.1-dev FP8 or GGUF | `models/diffusion_models` or `unet` / GGUF folder | Prefer FP8/GGUF for 12GB |
| Flux text encoders (CLIP-L, T5) | `models/clip` / `text_encoders` | Required by Flux graphs |
| Flux VAE (ae.safetensors) | `models/vae` | If not baked into checkpoint |
| IP-Adapter Plus Face / SDXL/Flux compatible | `models/ipadapter` + CLIP vision | Character consistency |
| 4x upscaler (RealESRGAN / similar) | `models/upscale_models` | Optional polish |

## Recommended sources

- Hugging Face: `black-forest-labs/FLUX.1-dev` (quantized community FP8/GGUF ports)
- Hugging Face / Civitai: IP-Adapter weights matching your Flux workflow
- Keep total working set sequential: **generate still → free VRAM → I2V**

## After downloads

1. Build Flux → Wan I2V graph in ComfyUI UI
2. Export **Save (API Format)** → `DirectorX/workflow_api.json`
3. Map node IDs in `config.py` → `NODE_MAP`
4. `python main.py`

## Disk estimate

Roughly **40–80GB** additional depending on Flux quant + IP-Adapter + upscalers.
