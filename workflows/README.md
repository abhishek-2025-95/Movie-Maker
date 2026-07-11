# ComfyUI workflow for DirectorX

## Goal graph (best quality on RTX 5070 12GB)

1. **Flux FP8 / GGUF** text-to-image (base still)
2. **IP-Adapter** (character mode only) — lock face/wardrobe from scene 0
3. **Wan 2.2 I2V FP8** — you already have:
   - `C:\ComfyUI\models\diffusion_models\wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors`
   - `C:\ComfyUI\models\diffusion_models\wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors`
   - `C:\ComfyUI\models\vae\wan_2.1_vae.safetensors`
4. Optional **upscale** (RTX VSR / ESRGAN)
5. **Save Video** / VHS Video Combine

## Export for automation

1. Open ComfyUI → Settings → enable **Dev Mode**
2. Build/load your graph and get one good manual render
3. Click **Save (API Format)**
4. Save/copy the file to project root as:

```
C:\Users\user\Documents\DirectorX\workflow_api.json
```

5. Open `config.py` and set `NODE_MAP` IDs to match:
   - `positive_prompt` → CLIP/Flux positive text node
   - `negative_prompt` → negative text node
   - `ksampler_seed` → sampler seed node
   - `save_prefix` → SaveVideo / VideoCombine filename_prefix
   - `ipadapter_image` → LoadImage used by IP-Adapter (character mode)
   - `width` / `height` → latent size node (optional)

## Starter custom nodes

Run `scripts\install_comfy_nodes.ps1` then restart ComfyUI.
