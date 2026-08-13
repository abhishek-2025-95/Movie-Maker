# Cinema Master Pipeline — Design

**Date:** 2026-08-05  
**Status:** Approved  
**Constraint:** RTX 5070 12GB local only; long renders in external terminal  
**Approach:** Master Pipeline Module (story-agnostic)

## Goal

Build a reusable **cinema_master** pipeline (upscale / face lock / audio / master) before any story. Any beat JSON can run on it afterward. Target: watchable short-film delivery quality on 12GB via Wan 480/720 hybrid + heavy post — not cloud, not Veo.

## Locked decisions

| Topic | Choice |
|-------|--------|
| Scope | Full pipeline first; stories consume it later |
| Resolution | Hybrid: close-ups Wan 480→1080; wides try 720, OOM→480 |
| Face lock | True IP-Adapter on Flux (`ComfyUI_IPAdapter_plus`); InstantID optional later |
| Audio | Local auto: Edge-TTS + local music gen + procedural Foley |
| Quant base | Keep Flux Q5 + Wan Q4; optional Wan Q5/Q6 probe as future flag |

## Architecture

```
story beat JSON (any theme)
        │
        ▼
┌─────────────────────┐
│  cinema_master      │  reusable, story-agnostic
│  orchestrator       │
└─────────┬───────────┘
          │
   ┌──────┼──────────────────────────────┐
   ▼      ▼                              ▼
Flux+IPAdapter    shot_tag → Wan            audio bed
bible + shots     close:480 / wide:720→fb   Edge-TTS + music + Foley
   │                    │                        │
   └────────┬───────────┘                        │
            ▼                                    │
      stitch (xfade/hard)                        │
            ▼                                    │
   Real-ESRGAN → 1080p + face restore            │
            ▼                                    │
      grade / grain / 24fps encode ◄─────────────┘
            ▼
   final_outputs/<title>_cinema_master.mp4
```

### Contracts

- **Input:** beat list `{id, plate, shot_tag: close|wide, prompt, motion, duration_hint, audio_cues}`
- **Output:** 1920×1080 (16:9) or 1080×1920 (9:16), 24fps, AAC, ~12–15 Mbps
- **Cache:** `temp/cinema_master/<run_id>/` per stage
- **Launch:** external `.bat` for long jobs

### Hard rules

1. Wan default close-ups stay 480; wide *tries* 720, OOM → 480 auto.
2. IP-Adapter required for character plates — fail loud if weights/nodes missing (no silent proof-quality degrade).
3. No story hardcoding inside `cinema_master`.

## Components

| Module | Job |
|--------|-----|
| `cinema_master/schema.py` | Beat JSON validate |
| `cinema_master/bible.py` | Flux + IP-Adapter hero refs + per-shot plates |
| `cinema_master/motion.py` | Wan two-pass; close→480, wide→720 try + fallback |
| `cinema_master/stitch.py` | Hard cut / short xfade by beat rules |
| `cinema_master/upscale.py` | Real-ESRGAN → 1080; optional face restore |
| `cinema_master/audio.py` | Edge-TTS + local music + procedural Foley |
| `cinema_master/master.py` | Grade, grain, vignette, 24fps H.264 |
| `cinema_master/run.py` | Orchestrator + CLI + external launcher |
| `assets/cinema/` | Weights checklist, music stubs, Foley params |

### Setup deps (pipeline, not story)

- Flux IP-Adapter weights + CLIP vision
- Real-ESRGAN + face-restore model
- Existing: Flux Q5 GGUF, Wan 2.2 Q4 MoE, `ComfyUI_IPAdapter_plus`, `ComfyUI-GGUF`

## Data flow

1. Load `beats.json` → validate schema  
2. Bible + plates → `stills/`  
3. Per beat Wan chunks → `chunks/`; record actual res (`480` or `720`)  
4. Stitch → `edit/rough.mp4`  
5. Upscale + face restore → `edit/1080.mp4`  
6. Mix audio → `edit/mix.wav`  
7. Master → `final_outputs/<title>_cinema_master.mp4` + `run_report.json`

## Error handling

- Missing IP-Adapter / upscale weights → hard fail + install checklist  
- Wan 720 OOM → log `fallback_480`, continue  
- Comfy dead mid-run → restart once, resume unfinished beat  
- Audio fail → video still written; `audio_failed` in report (`--require-audio` to hard fail)

## Testing

- Schema + shot-tag→size routing unit tests (no GPU)  
- Upscale/audio/master dry-run with tiny fixture frames  
- Smoke: 1 close + 1 wide beat via external terminal  

## Success criteria

- Any story JSON runs without editing `cinema_master` code  
- Close path always delivers 1080 master; wide attempts 720 when possible  
- IP-Adapter plates logged (not prompt-only bible)  
- Auto audio bed present (no sine-only final)  
- Report proves Flux + IP-Adapter + Wan 2.2 + upscale chain  

## Out of scope (v1)

CrewAI, lip-sync, RIFE 60fps, native InstantID node, cloud music APIs, full feature runtime.

## First consumer (after pipeline green)

Victorian forbidden love (or any theme) as beat JSON only — no pipeline forks.
