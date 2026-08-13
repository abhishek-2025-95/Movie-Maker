# Autonomous DirectorX — finalized

User provides one line in `topics.txt`. Pipeline:

1. **Hollywood Director LLM** (`director.HOLLYWOOD_DIRECTOR_SYSTEM_PROMPT`) → 3-act JSON
2. **Flux FP8** stills @ 768×1344 + hardcoded `FLUX_NEGATIVE_PROMPT`
3. **VRAM flush** `/free` between Flux and Wan
4. **Master-still / IP-Adapter lock** — Scene-1 still → Scenes 2–3 Wan
5. **Premium captions** — Montserrat, yellow/white, black stroke ≥3, ≤6 words/line, spacing cleanup

Default: `SCENES_PER_VIDEO=3`.
