# Polish guards from SD1.5 horror QA (2026-07-12)

Approved fixes applied before Flux Option C dry-run:

1. **Anatomy negatives** — `config.ANATOMY_NEGATIVE` always merged in `style_prompts` + `comfy_runner`.
2. **Typography** — `cleanup_caption_text()`, yellow/white fill + black stroke ≥3px; CSS word spacing.
3. **Horror camera LLM** — director system prompt + `_enrich_visual_prompt` + horror fallback beats.
4. **Scene-1 ref lock** — `REQUIRE_SCENE1_REF_LOCK`; pipeline feeds Scene-1 still into Flux when `NODE_MAP_FLUX["ipadapter_image"]` is set.

**IP-Adapter status:** ComfyUI has `IPAdapter*` nodes. Weights (`ip-adapter-plus_sd15` + CLIP vision) downloading for interim; Flux-native IP-Adapter wires at Option C cutover once FP8 verifies.
