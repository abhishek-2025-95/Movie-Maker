# Quality OS P1 — Weights Install

**Goal:** Real-ESRGAN generative upscale + Flux IP-Adapter (XLabs) face/style lock on GGUF.

## Run (external PowerShell)

```powershell
cd C:\Users\user\Documents\DirectorX
powershell -ExecutionPolicy Bypass -File scripts\download_quality_os_p1_weights.ps1
```

Then restart ComfyUI so `x-flux-comfyui` nodes load.

## Expected layout

| Asset | Path |
|-------|------|
| RealESRGAN x2 | `C:\ComfyUI\models\upscale_models\RealESRGAN_x2plus.pth` |
| Flux IP-Adapter | `C:\ComfyUI\models\xlabs\ipadapters\ip_adapter.safetensors` |
| CLIP Vision L | `C:\ComfyUI\models\clip_vision\clip-vit-large-patch14.safetensors` |
| Custom node | `C:\ComfyUI\custom_nodes\x-flux-comfyui\` |

## Verify

```powershell
.\.venv\Scripts\python.exe -c "from quality_os.preflight import check_p1; print(check_p1())"
```

`ok=True` means weights + node present. Flux IP-Adapter stills use `workflows/flux_t2i_ipadapter_gguf_api.json` when ready.

## XLabs + modern ComfyUI (`attn_mask`)

If IP-Adapter KSampler fails with `DoubleStreamBlock.forward() got an unexpected keyword argument 'attn_mask'`, patch:

`C:\ComfyUI\custom_nodes\x-flux-comfyui\xflux\src\flux\modules\layers.py`

`DoubleStreamBlock.forward` must accept `attn_mask=None, transformer_options=None, **attention_kwargs` and pass them through to `self.processor(...)`. Restart Comfy after editing.
