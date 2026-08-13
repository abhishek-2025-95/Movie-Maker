# Flux + Wan Cinematic Engine (Option C) — Design

**Status:** Approved (Option C). Current RV horror render must finish uninterrupted; implement after it completes.

**Goal:** Highest practical cinematic stills on RTX 5070 12GB via verified Flux.1-dev, then Wan 2.2 I2V motion — never downgrade to SD1.5/Realistic Vision for live output. Fix VRAM via sequential execution + flush, not weaker models.

## Non-negotiables

1. **Still engine = Flux.1-dev** (FP8 primary, GGUF Q6/Q5 fallback). Realistic Vision / Anything V5 / SD1.5 banned for live cinematic path.
2. **Motion engine = Wan 2.2 FP8 I2V** from the Flux still.
3. **Sequential VRAM:** Flux → ComfyUI `/free` (unload + free) → Wan → `/free` again. Never co-resident.
4. **Still resolution:** min **768×1344** (9:16), **20–25 steps**.
5. **Export:** MoviePy **1080×1920**, bitrate **15000k**.
6. **Gray-frame mitigation:** SHA-256 verify downloads; detect near-solid stills; prefer **VAEDecodeTiled** (or TAESD only as last-resort decode path if tiled still OOMs).

## Option C hierarchy

```
try:
  Flux FP8 checkpoint (SHA-verified)
  → still @ 768x1344, tiled VAE decode
  → reject if gray/corrupt
except OOM or gray/corrupt:
  Flux GGUF Q6 (then Q5)
  → same still graph variant
→ free VRAM
→ Wan 2.2 I2V from accepted still
→ free VRAM
→ assemble @ 15000k
```

## Gray frames — root causes we treat

| Cause | Fix |
|--------|-----|
| Corrupt FP8 download (size-matched, bad hash) | SHA-256 gate before any render |
| VAE decode VRAM spike on 12GB | `VAEDecodeTiled` in Flux graph; flush before Wan |
| Wrong checkpoint silently swapped to SD1.5 | Config `STILL_BACKEND=flux_only`; refuse RV |

## Components to change (post-render)

- `config.py` — sizes 768×1344, `FLUX_STEPS=20..25`, `STILL_BACKEND`, model paths, bitrate already 15000k
- `scripts/build_workflow_api.py` — real Flux graph + tiled VAE; GGUF graph variant
- `scripts/download_flux.ps1` — FP8 + GGUF + SHA verify (no silent “present” if hash wrong)
- `pipeline.py` — Option C fallback + gray-frame reject + keep sequential flush
- `utils.py` / new helper — `is_gray_or_blank_image()`, stronger `/free` wait
- Docs — `scripts/download_models.md`

## Explicitly out of scope this pass

- Claiming true Netflix finishing (grading suite, plate photography, etc.)
- Re-enabling animated / SD1.5 for live topics
- Interrupting the in-flight horror Short render
