# 12GB Max Quality (Open Source) — Design

**Status:** Approved  
**Constraint:** RTX 5070 12GB only — no cloud, no Veo  
**Bible source:** Flux-generated (no user photo)

## Goal

Raise local wingsuit / action reels from ~6.8 toward the practical OSS ceiling (~7.8–8.2) by fixing suit DNA before Wan, not by swapping video models.

## Architecture

```
suit bible (Flux × N, reject fantasy wings)
  → FPV beat (no identity lock; multi-seed pick)
  → body beats (identity from bible + fabric prompts)
  → Wan 2.2 14B FP8 I2V @ 480 (default), optional 512 try
  → hard Comfy restart between Flux/Wan
  → assemble + sharper upscale to 1080×1920
```

## Non-negotiables

1. Motion engine stays **Wan 2.2 I2V** (already best fit for 12GB).
2. Wan **480** remains the stable default; 512 is best-effort with fallback.
3. Never identity-lock from FPV plates.
4. LightX2V speed LoRAs stay **out** of the Wan graph for quality finals (already unused).

## Out of scope

Hunyuan full, LTX 13B, Wan 720 long, commercial APIs, IPAdapter until weights exist.
