# Cinematic Narrative Engine — Design

**Goal:** Upgrade DirectorX from “pretty clips” to directed storytelling: Setup → Conflict → Climax with camera/lighting intent.

**Approved direction (user):** Visuals are cinematic; narrative/pacing must catch up. Run a real ~30s horror project (not a tech dry-run).

## Engine rules

1. **3-act script before render** — every horror/suspense topic maps to Setup / Conflict / Climax with named emotional beats.
2. **Director directives** — each scene carries lighting + camera language baked into `visual_prompt` and `motion_prompt` (low-key, dolly/push, claustrophobic framing, etc.).
3. **Pacing** — ~30s = 6 scenes × ~5s; slower motion prompts (hold, crawl, delayed reveal) vs twitchy faces.
4. **Character lock** — Scene-1 master still reused (existing `CHARACTER_MASTER_STILL_LOCK`).

## Deliverable this pass

- Rewrite horror fallback + LLM system prompt for narrative engine
- Topic: 30s hospital horror with clear BME
- Render: `python main.py --topics topics_narrative_horror.txt --scenes 6 -v`
