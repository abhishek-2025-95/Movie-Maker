# Quality OS Upgrade — Design

**Date:** 2026-08-05  
**Status:** Approved  
**Approach:** Quality OS upgrade (factory-first)  
**Mandate:** `.cursor/rules/quality-first-cinematic.mdc` — no quality/time compromise  
**Audit:** `docs/plans/2026-08-05-pipeline-quality-audit.md`

## Goal

Raise DirectorX’s **default** local path to the maximum practical cinematic quality on RTX 5070 12GB by wiring battle-tested premium patterns into the main factory, then adding identity (IP-Adapter / LoRA) and generative upscale.

## Architecture

```
Flux Q5 (≥24 steps) + hero / IP-Adapter / LoRA
        ↓
Wan 2.2 TWO-PASS ONLY (steps≥14, CFG~4.5, 480 native)
        ↓
chunk plan + xfade (NO freeze-pad)
        ↓
1080 master: Real-ESRGAN if present else sleep317 HQ chain
        ↓
lighter grade + audio + captions → final + run_report.json
```

**Hard rules**
- Finals use `wan_two_pass_moe`; single-process dual-UNET deprecated for quality path
- `QUALITY_FIRST=True` drives steps/CFG/upscale/no-freeze defaults
- Missing optional weights → logged fallback (never silent unexplained degrade)
- Long jobs → external terminal

## Phases

| Phase | Scope |
|-------|--------|
| **P0** | Config + pipeline two-pass + steps/CFG + HQ upscale + kill freeze-pad on quality profiles |
| **P1** | Real-ESRGAN + IP-Adapter weights/preflight + Flux IP-Adapter workflow |
| **P2** | Character LoRA train toolkit + A/B proof reel |
| **P3** | Optional Wan Q5 probe; RIFE 16→24 |

## Errors

- Two-pass fail → one restart retry; no Ken Burns success on quality profiles  
- Real-ESRGAN missing → sleep317 HQ ffmpeg + report flag  
- IP-Adapter required but missing → hard fail  

## Success

- Default path = two-pass + HQ 1080  
- Reports prove steps/CFG/upscale/two_pass  
- P1/P2 add identity without weakening P0  

## Out of scope (v1)

Cloud APIs, InstantID-first, Wan 720 as default, CrewAI.
