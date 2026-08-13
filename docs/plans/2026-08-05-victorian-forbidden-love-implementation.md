# Victorian Forbidden Love Proof — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Render a ~30–35s Victorian forbidden-love cinematic proof via Flux GGUF + Wan 2.2 GGUF two-pass, launched only from an external terminal.

**Architecture:** Hardcoded 4-beat shot list with locked character bible → Flux stills → Wan two-pass clips → ffmpeg xfade assemble → final MP4. No CrewAI in this pass.

**Tech Stack:** DirectorX `comfy_runner`, `wan_two_pass_moe`, Flux/Wan GGUF workflows, ffmpeg, external `.bat` launcher.

---

### Task 1: Render script

**Files:**
- Create: `scripts/render_victorian_forbidden_love.py`
- Create: `scripts/run_victorian_forbidden_external.bat`

**Step 1:** Implement 4-beat prompts + Flux stills + Wan two_pass_wan (len=81) + xfade stitch + optional light audio bed.

**Step 2:** Bat launches live console + log under `temp/victorian_forbidden/`.

### Task 2: External run

**Step 1:** Start bat in external `cmd /k` (user requirement).

**Step 2:** Verify `final_outputs/Victorian_Forbidden_Love_Proof.mp4` exists and duration ~30s+.

---
