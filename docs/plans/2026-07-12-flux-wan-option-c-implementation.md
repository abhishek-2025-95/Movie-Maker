# Flux + Wan Option C Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enforce verified Flux.1-dev stills (FP8 → GGUF fallback) + Wan 2.2 I2V with sequential VRAM flush, 768×1344, tiled VAE, 15000k export — ban SD1.5 for live.

**Architecture:** TWO_STAGE pipeline already exists; restore real Flux graphs, add SHA gate + gray reject + GGUF fallback, bump still resolution, keep `/free` between stages.

**Tech Stack:** ComfyUI API, Flux.1-dev FP8/GGUF, Wan 2.2 FP8, MoviePy, PowerShell download + SHA256

**Gate:** Do not swap live workflows until current horror render exits. Prep scripts/docs anytime; cutover after process 750462 finishes.

---

### Task 1: Hard ban SD1.5 for live stills in config

**Files:**
- Modify: `config.py`

**Step 1:** Set `RATIO_SIZES["9:16"] = (768, 1344)`, `FLUX_STEPS = 22`, `STILL_BACKEND = "flux"`, `FLUX_CKPT_FP8`, `FLUX_CKPT_GGUF`, expected SHA256 for FP8 (`8e91b68084b53a7fc44ed2a3756d821e355ac1a7b6fe29be760c1db532f3d88a`), `EXPORT_BITRATE = "15000k"` (already), `ALLOW_SD15_STILLS = False`.

**Step 2:** Comment that Realistic Vision must not be referenced by live Flux workflow builder.

---

### Task 2: SHA-verified download script (FP8 + GGUF)

**Files:**
- Modify: `scripts/download_flux.ps1`
- Modify: `scripts/download_models.md`
- Create: `scripts/verify_flux_checkpoint.py`

**Step 1:** `download_flux.ps1` downloads FP8; verifies SHA256; deletes/rejects mismatch; downloads GGUF Q6 (and Q5 optional) under `models/unet` or Comfy GGUF path used by loader.

**Step 2:** `verify_flux_checkpoint.py` exits 0 only if size+hash OK.

**Step 3:** Update `download_models.md` with Option C + hash.

---

### Task 3: Rebuild Flux API graph with tiled VAE

**Files:**
- Modify: `scripts/build_workflow_api.py` → `flux_t2i_workflow()`
- Create: optional `flux_t2i_gguf_api.json` builder path

**Step 1:** Replace Realistic Vision CheckpointLoader graph with Flux FP8 CheckpointLoaderSimple + FluxGuidance + proper sampler chain OR documented all-in-one FP8 checkpoint graph that Comfy accepts.

**Step 2:** Use `VAEDecodeTiled` (tile_size ~512) instead of `VAEDecode`.

**Step 3:** Run `python scripts/build_workflow_api.py` and refresh `NODE_MAP_FLUX` in config if IDs change.

---

### Task 4: Gray-frame detector + Option C fallback in pipeline

**Files:**
- Modify: `utils.py` or Create: `image_qc.py`
- Modify: `pipeline.py`

**Step 1:** `is_unusable_still(path)` — low variance / near-constant RGB → True.

**Step 2:** After Flux FP8 still: if missing/OOM/gray → free VRAM → run GGUF workflow → re-check.

**Step 3:** If both fail → log error, skip scene (do not silently call SD1.5).

**Step 4:** Keep existing `free_comfyui_memory` between Flux and Wan; optionally increase sleep to 5s after unload.

---

### Task 5: Smoke test then first cinematic topic

**Files:** none (runtime)

**Step 1:** ComfyUI up with `--lowvram`.

**Step 2:** One Flux still @ 768×1344; visually not gray/anime.

**Step 3:** One Wan clip from that still.

**Step 4:** Full short topic only after smoke passes.

---

### Task 6: Docs + architecture note

**Files:**
- Modify: `README.md` architecture section (Flux only for live)
- Keep: `docs/plans/2026-07-12-flux-wan-cinematic-engine-design.md`
