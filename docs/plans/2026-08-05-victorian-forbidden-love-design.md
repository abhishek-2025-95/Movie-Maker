# Victorian Forbidden Love — Cinematic Proof Design

**Date:** 2026-08-05  
**Status:** Approved (Approach A + tone 3)  
**Constraint:** All renders run in an **external terminal** (not Cursor-tied).

## Goal

One ~30–35s professional-feeling Victorian **forbidden passion** beat on local RTX 5070 GGUF stack (Flux Q5 → Wan 2.2 Q4 two-pass), proving cinema look before CrewAI / full film.

## Creative

- **Setting:** Candlelit parlor, late evening, 1880s England.
- **Tone:** Passionate, risk of being seen (almost-kiss, interrupted).
- **Beats:** (1) Hold / eyes (2) Almost-touch heat (3) Threat / door glance (4) Break / composure.

## Tech

| Stage | Choice |
|-------|--------|
| Stills | Flux GGUF `flux_t2i_gguf_api.json`, 768×1344 |
| Motion | Wan 2.2 GGUF two-pass MoE, 480×832, length≤81 (~5s), xfade stitch if needed |
| Face lock | Shared character bible in every Flux prompt + same seed offsets |
| Audio | Minimal: room tone + soft door cue + quiet strings (optional Edge/local) |
| Output | `final_outputs/Victorian_Forbidden_Love_Proof.mp4` |
| Launch | `scripts/run_victorian_forbidden_external.bat` |

## Out of scope

CrewAI agents, 4K/RIFE, multi-location arc, heavy TTS dialogue, LoRAs.

## Success criteria

- Faces readable and consistent across 4 beats  
- Real Wan motion (no freeze-pad pauses)  
- Forbidden beat reads clearly without dialogue  
- Completes on 12GB with `--normalvram` without crash  
