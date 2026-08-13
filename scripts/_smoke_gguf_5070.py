"""Smoke Flux (GGUF if ready else FP8) + Wan two-pass length=81 for 5070 GGUF profile."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

import config
from comfy_runner import apply_scene_to_workflow, load_workflow, pick_best_output, run_workflow
from utils import new_client_id, restart_comfyui
from wan_two_pass_moe import two_pass_wan

config.refresh_workflow_paths()
print("FREE_GB", round(__import__("shutil").disk_usage("C:/").free / 1e9, 1))
print("FLUX_WF", config.resolve_workflow_flux())
print("WAN_WF", config.resolve_workflow_wan())
assert restart_comfyui(wait_sec=150)

wf = load_workflow(config.resolve_workflow_flux())
job = apply_scene_to_workflow(
    wf,
    visual_prompt="cinematic couple under blue umbrella rain metro photoreal faces",
    motion_prompt="",
    filename_prefix="dx_smoke_gguf_flux_still",
    width=768,
    height=1344,
    node_map=config.NODE_MAP_FLUX,
    include_motion_in_prompt=False,
    cinematic_suffix=config.STYLE_SUFFIX["live"],
    negative_prompt=config.FLUX_NEGATIVE_PROMPT,
    seed=42,
)
print("QUEUE_FLUX", config.resolve_workflow_flux().name)
_, paths = run_workflow(job, client_id=new_client_id(), timeout_s=1800)
best = pick_best_output(paths, "dx_smoke_gguf_flux_still", allow_stale_disk=True)
# pick_best_output only accepts images when prefix contains "_still"
if best is None:
    from comfy_runner import latest_files_with_prefix

    cands = [
        p
        for p in latest_files_with_prefix("dx_smoke_gguf_flux")
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    best = cands[0] if cands else None
print("FLUX_OK", best, best.stat().st_size if best else None)

still = Path(best) if best else None
if still is None or not still.exists():
    still = ROOT / "temp" / "romance_wan_premium_v5" / "dx_rom_v5_s00_still.png"
if not still.exists():
    still = ROOT / "temp" / "romance_wan_premium_v4" / "dx_rom_wan_s00_still.png"
assert still.exists(), still
print("WAN_STILL", still)

out = ROOT / "temp" / "dx_smoke_gguf_wan81.mp4"
print("QUEUE_WAN", config.resolve_workflow_wan().name, "still", still)
two_pass_wan(
    still,
    visual="couple rain soft blinks readable faces",
    motion="soft blinks rain",
    prefix="dx_smoke_gguf_wan81",
    seed=11,
    neg=config.FLUX_NEGATIVE_PROMPT,
    out_mp4=out,
    ww=480,
    wh=832,
    length=81,
    steps=10,
    cfg=4.5,
)
print("WAN_OK", out, out.stat().st_size)
print("ALL_DONE")
