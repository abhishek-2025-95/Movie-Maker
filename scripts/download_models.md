# Model download checklist — RTX 5070 12GB + Ryzen 9800X3D GGUF profile

## Policy (5070 sweet spot)

| Stage | Model | Quant | Why |
|-------|--------|-------|-----|
| Still (T2I) | Flux.1-dev GGUF | **Q5_K_S** | city96 does not publish Q5_K_M; Q5_K_S is the K-quant quality pick. Avoid Q3 (blurry) and Q6/Q8 (VRAM thrash). |
| Motion (I2V) | Wan 2.2 14B MoE GGUF | **Q4_K_M** × high+low | ~9.65GB each — golden for 12GB; ~95% of FP8 fidelity. |
| Text | T5XXL FP8 + CLIP-L | safetensors | CLIPLoader `device=cpu` → 9800X3D + 32GB RAM; VRAM stays for UNET. |
| VAE | Flux `ae.safetensors` / Wan `wan_2.1_vae` | — | Wan/Flux decode with **tile_size=512**. |

Comfy launch: **`--normalvram`** (not `--lowvram`).

## One-command GGUF download

```powershell
cd C:\Users\user\Documents\DirectorX
# Need ~40GB+ free on C: (pagefile + intermediates). Target 100GB+ free for comfort.
powershell -ExecutionPolicy Bypass -File .\scripts\download_gguf_5070.ps1
python scripts\build_workflow_api.py
python -c "import config; config.refresh_workflow_paths(); print(config.WORKFLOW_FLUX); print(config.WORKFLOW_WAN); print(config.still_backend())"
```

Downloads:
- `models/unet/flux1-dev-Q5_K_S.gguf`
- `models/unet/wan2.2_i2v_high_noise_14B_Q4_K_M.gguf`
- `models/unet/wan2.2_i2v_low_noise_14B_Q4_K_M.gguf`
- `models/text_encoders/t5xxl_fp8_e4m3fn.safetensors`
- `models/text_encoders/clip_l.safetensors`
- `models/vae/ae.safetensors` (BFL gated — `huggingface-cli login` if needed)

Legacy FP8 Flux still download (fallback if AE gated):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\download_flux.ps1
```

## Storage warning

If C: is **>90% full**, Windows pagefile cannot expand and Comfy dies mid-job (`torch_cpu.dll`). Keep **≥40GB free** (ideally 100–150GB) before long Wan runs.

## After download

DirectorX auto-selects GGUF workflows when files exist (`USE_GGUF_5070_PROFILE=True` in `config.py`).
Two-pass Wan MoE (`scripts/wan_two_pass_moe.py`) uses `resolve_workflow_wan()` so it picks GGUF automatically.
