# 12GB Max Quality OSS Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Suit-bible reject loop + body identity lock + Wan quality knobs + sharper export for action reels on 12GB.

**Architecture:** Pre-roll Flux suit plates scored against fantasy-wing heuristics; winner becomes `character_ref` for non-FPV beats. Wan stays 480 default with optional 512 try. Export uses sharper ffmpeg scale.

**Tech Stack:** DirectorX pipeline, Flux FP8, Wan 2.2 I2V, ComfyUI, pytest, MoviePy/ffmpeg

---

### Task 1: Suit-wing reject heuristic + config

**Files:**
- Modify: `config.py`
- Modify: `pipeline.py` (`_score_suit_bible_still`)
- Test: `tests/test_wingsuit_action_reel.py`

**Steps:** Add `ACTION_SUIT_BIBLE_*` config; score stills (penalize butterfly orange/black wing patterns, reward matte black body + modest orange panels); unit-test scores.

### Task 2: Suit bible pre-roll in pipeline

**Files:**
- Modify: `pipeline.py` (before scene loop when `action_flight` / `wingsuit_15s`)
- Modify: `director.py` raw flag `suit_bible: True`

**Steps:** Generate N Flux bible stills with technical-suit prompt; pick best score; stage as `ref_{slug}.png`; skip FPV for lock.

### Task 3: Wan quality knobs + sharper upscale

**Files:**
- Modify: `config.py` (`WAN_QUALITY_STEPS`, optional `WAN_QUALITY_TRY_512`)
- Modify: `comfy_runner.py` / `pipeline.py` to bump Wan steps for action
- Modify: `editor.py` `_ffmpeg_upscale` (lanczos + light unsharp)

### Task 4: Tests + wingsuit render

**Steps:** pytest wingsuit tests; fire `main.py` wingsuit topic; frame-check suit DNA.
