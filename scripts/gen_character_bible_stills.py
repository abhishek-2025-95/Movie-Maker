"""P2 — generate Flux character bible stills for LoRA training (external).

Identity locked to AR Filter Horror viewer from the production prompt.
Writes images + matching .txt captions into assets/characters/<slug>/bible/
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from comfy_runner import (
    apply_scene_to_workflow,
    load_workflow,
    pick_best_output,
    run_workflow,
)
from utils import new_client_id, restart_comfyui

log = logging.getLogger("p2_bible")

SLUG = "ar_filter_viewer"
TRIGGER = "dxc_arviewer"
WORK = ROOT / "assets" / "characters" / SLUG / "bible"
STILL_W, STILL_H = 768, 1344
SEED = 20260806
COOLDOWN = 10

IDENTITY = (
    f"{TRIGGER}, same young adult identity lock every frame: mid-20s person, "
    f"tired pale face, dark circles under eyes, messy dark hair, oversized dark hoodie, "
    f"scared but curious expression, photorealistic skin"
)
NEG = (
    "cartoon, anime, watermark, logo, deformed hands, extra fingers, blurry, lowres, "
    "bright daylight, smiling influencer, crowd, multiple people, text overlay"
)

# 15 varied plates — angles / light / framing for strong Flux LoRA
SHOTS = [
    "front portrait close-up, dim bathroom night light, phone screen glow on face",
    "three-quarter portrait left, 3AM bedroom, soft underexposed noir",
    "three-quarter portrait right, mirror edge visible, low key lighting",
    "medium shot holding smartphone, bathroom mirror behind, found-footage",
    "over-shoulder looking into bathroom mirror, face in reflection sharp",
    "close-up eyes and forehead, fear micro-expression, film grain",
    "profile left silhouette rim-lit by phone, dark room",
    "profile right, hoodie hood half-up, cold bathroom tiles",
    "medium close-up looking down at phone, screen glow cyan-white",
    "head and shoulders facing camera, empty dark bedroom bokeh",
    "slight low angle looking scared upward, ceiling dark",
    "slight high angle looking down, vulnerable, noir contrast",
    "tight face crop, pores visible, tired 3AM realism",
    "medium shot turning head looking behind, tense, empty room",
    "mirror selfie angle holding phone, authentic bathroom night ambience",
]


def _ensure_comfy() -> None:
    import urllib.request

    url = f"http://{config.COMFYUI_HOST}/system_stats"
    for attempt in range(8):
        try:
            urllib.request.urlopen(url, timeout=5)
            return
        except Exception:
            time.sleep(2.0 + attempt)
    if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
        raise RuntimeError("ComfyUI failed to start")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    WORK.mkdir(parents=True, exist_ok=True)
    config.refresh_workflow_paths()
    meta = {
        "slug": SLUG,
        "trigger": TRIGGER,
        "topic": "The Filter That Knows Your Reflection",
        "niche": "Modern Smartphone Horror / AR / Psychological Thriller",
        "shots": len(SHOTS),
    }
    (WORK.parent / "character.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print("=== P2 Character Bible ===", flush=True)
    print(f"slug={SLUG} trigger={TRIGGER} out={WORK} n={len(SHOTS)}", flush=True)
    if not config.gguf_flux_ready():
        raise RuntimeError("Flux GGUF not ready")

    print("COMFY_RESTART", flush=True)
    restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120)))

    wf_path = ROOT / "workflows" / "flux_t2i_gguf_api.json"
    nm = json.loads((ROOT / "workflows" / "node_map_flux_gguf.json").read_text(encoding="utf-8"))
    done = 0
    for i, shot in enumerate(SHOTS):
        dest = WORK / f"bible_{i:02d}.png"
        cap = WORK / f"bible_{i:02d}.txt"
        caption = (
            f"{TRIGGER}, {IDENTITY}, cinematic 9:16 vertical, {shot}, "
            f"extremely low-light found-footage, film noir grading, sharp face detail"
        )
        cap.write_text(caption + "\n", encoding="utf-8")
        if dest.exists() and dest.stat().st_size > 40_000:
            print(f"REUSE {dest.name}", flush=True)
            done += 1
            continue
        _ensure_comfy()
        prefix = f"p2_bible_{SLUG}_{i:02d}"
        wf = load_workflow(wf_path)
        job = apply_scene_to_workflow(
            wf,
            visual_prompt=caption,
            motion_prompt="",
            filename_prefix=prefix,
            width=STILL_W,
            height=STILL_H,
            node_map=nm,
            include_motion_in_prompt=False,
            cinematic_suffix=config.STYLE_SUFFIX.get("live", config.CINEMATIC_SUFFIX),
            negative_prompt=NEG,
            seed=SEED + i * 13,
        )
        print(f"FLUX {i+1}/{len(SHOTS)} {dest.name}", flush=True)
        _, paths = run_workflow(job, client_id=new_client_id(), timeout_s=2400)
        best = pick_best_output(paths, prefix, allow_stale_disk=True)
        if best is None:
            from comfy_runner import latest_files_with_prefix

            imgs = [
                p for p in latest_files_with_prefix(prefix)
                if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            ]
            best = imgs[0] if imgs else None
        if not best:
            raise RuntimeError(f"Bible still missing: {prefix}")
        shutil.copy2(best, dest)
        print(f"OK {dest}", flush=True)
        done += 1
        time.sleep(COOLDOWN)

    print(f"BIBLE_DONE {done}/{len(SHOTS)} -> {WORK}", flush=True)
    print("NEXT: run scripts/run_p2_train_character_lora_external.bat", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
