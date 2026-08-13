# Horror Jump-Scare Short — Design

**Date:** 2026-07-12  
**Status:** Approved  
**Output:** one English 9:16 cinematic Short (~40s)

## Concept

Abandoned hospital hallway → dead elevator → same-floor loop → jump scare inches from lens.

## Specs

| Field | Value |
|-------|--------|
| Mode | character |
| Style | live (cinematic horror grade) |
| Lang | en |
| Ratio | 9:16 |
| Scenes | 8 tight beats, one location chain |
| Captions | PyCaps (`francozanardi/pycaps`) template `hype` |

## Story beats

1. Flickering hallway — warning  
2. Footsteps that aren’t yours  
3. Elevator opens empty  
4. Descent — lights die  
5. Whisper: turn around  
6. Doors open on the same floor  
7. Hold / breath  
8. Jump scare face → cut to black  

## Pipeline

Still (checkpoint) → Wan I2V (no LightX2V LoRA) → assemble A/V without MoviePy captions → PyCaps burn-in.

## Success criteria

- Cause→effect continuity (no random scene hops)  
- One hard scare payoff  
- Premium kinetic English subtitles via PyCaps  
