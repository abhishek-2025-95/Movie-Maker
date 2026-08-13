# DirectorX Pipeline Quality Audit

**Date:** 2026-08-05  
**Hardware:** RTX 5070 12GB · Flux Q5 GGUF · Wan 2.2 Q4 MoE  
**Mandate:** Quality over time — no compromise defaults  

## Verdict

Default `pipeline.py` path is **social/reel tier**. Premium scripts (Victorian v2, Sleep 317) are closer to **this machine’s ceiling** but still soft vs theatrical cinema. Biggest gap: **main pipeline does not use the battle-tested two-pass Wan path.**

## Top killers (impact order)

1. Wan native **480p** → lanczos 1080 (soft faces)  
2. Flux still downscaled hard into Wan canvas before motion  
3. `pipeline.py` **skips** `wan_two_pass_moe` (dual-UNET / OOM / fallbacks)  
4. Wan **Q4** + often **10 steps** in scripts (sleep317 at 14 is better)  
5. No IP-Adapter / LoRA identity lock  
6. Freeze-pad to beat length  
7. 16fps Wan → 24fps export without RIFE  
8. Lanczos-only upscale (no Real-ESRGAN)  
9. Heavy grain on soft source  
10. Procedural / Edge audio vs scored mix  

## Already good

Two-stage Flux→Wan · GGUF 12GB profile · Comfy restart hygiene · tiled VAE · premium two-pass MoE · hero-plate crops (Victorian) · chunk+xfade planning · 15Mbps export  

## Max-quality ROI order (local only)

1. Wire **all** Wan through `two_pass_moe`  
2. Hero-plate (+ later IP-Adapter / LoRA)  
3. Wan steps **14+**, CFG **4.5**  
4. Sleep317-class upscale/grade globally  
5. Kill freeze-pad via chunk planning  
6. Flux steps 24–25  
7. Install Real-ESRGAN + IP-Adapter weights  
8. Character LoRA train for cast lock  
9. Optional Wan Q5 probe (two-pass only)  
10. Optional RIFE 16→24  

## Honest ceiling

Watchable cinematic **short / reel** on 12GB is achievable. True theatrical 1080p motion detail is not. “100% character lock” needs LoRA/IP-Adapter work — not prompt marketing.
