# P2 — Flux Character LoRA (12GB)

**Character:** AR Filter Horror viewer (`dxc_arviewer`)  
**Prompt source:** *The Filter That Knows Your Reflection*

## Pipeline

1. **Bible stills** (Flux GGUF, 15 plates)  
   `scripts/run_p2_bible_external.bat`
2. **Train LoRA** (ostris/ai-toolkit, `low_vram` + quantize)  
   `scripts/run_p2_train_character_lora_external.bat`  
   Needs HuggingFace access to `black-forest-labs/FLUX.1-dev` (`HF_TOKEN`).
3. **Install** → `C:\ComfyUI\models\loras\dxc_arviewer.safetensors`
4. **Render** horror with IP-Adapter + LoRA workflow  
   `workflows/flux_t2i_ipadapter_lora_gguf_api.json`

## Trigger word

Put `dxc_arviewer` in Flux positives when LoRA is loaded (strength ~0.85).

## Notes

- Training downloads FLUX.1-dev (gated). Accept license on HF first.
- 12GB: resolution 512/768, rank 16, 1500 steps, sampling disabled during train.
- Inference stays on Flux Q5 GGUF + `LoraLoaderModelOnly`.
