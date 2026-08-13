"""Two-process Wan MoE: high-noise SaveLatent → Comfy restart → low-noise LoadLatent.

Avoids loading both 14B UNETS in one process (torch_cpu.dll AV on RTX 5070).
"""
from __future__ import annotations

import logging
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from comfy_runner import apply_scene_to_workflow, load_workflow, pick_best_output, run_workflow
from utils import new_client_id, restart_comfyui

log = logging.getLogger("wan_two_pass")


def _stage_still(still: Path, name: str, size: tuple[int, int]) -> str:
    from PIL import Image

    config.COMFYUI_INPUT.mkdir(parents=True, exist_ok=True)
    dest = config.COMFYUI_INPUT / name
    Image.open(still).convert("RGB").resize(size, Image.LANCZOS).save(dest, format="PNG")
    return name


def _find_latent(prefix: str, after_ts: float) -> Path | None:
    roots = [
        Path(config.COMFYUI_OUTPUT) / "latents",
        Path(config.COMFYUI_OUTPUT),
        Path(getattr(config, "COMFYUI_INPUT", config.COMFYUI_OUTPUT)),
    ]
    cands: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.latent"):
            if prefix.replace("/", "_") in p.name or prefix.split("/")[-1] in p.name:
                if p.stat().st_mtime >= after_ts - 2:
                    cands.append(p)
        # also match filename_prefix style ComfyUI_00001_.latent
        for p in root.rglob(f"*{prefix.split('/')[-1]}*.latent"):
            if p.stat().st_mtime >= after_ts - 2 and p not in cands:
                cands.append(p)
    if not cands:
        # newest latent anywhere under output
        for root in roots:
            if root.exists():
                for p in root.rglob("*.latent"):
                    if p.stat().st_mtime >= after_ts - 2:
                        cands.append(p)
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def _stage_latent_for_load(latent_path: Path) -> str:
    """Copy .latent into Comfy input so LoadLatent dropdown can see it."""
    dest_dir = Path(config.COMFYUI_INPUT)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / latent_path.name
    if dest.resolve() != latent_path.resolve():
        shutil.copy2(latent_path, dest)
    return dest.name


def run_high_pass(
    *,
    still: Path,
    visual: str,
    motion: str,
    prefix: str,
    seed: int,
    neg: str,
    ww: int,
    wh: int,
    length: int,
    steps: int,
    cfg: float,
    half: int,
) -> Path:
    if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
        raise RuntimeError("Comfy restart before high-pass failed")
    ref = _stage_still(still, f"{prefix}_{ww}x{wh}.png", (ww, wh))
    latent_prefix = f"latents/{prefix}_hi"
    t0 = time.time()
    wf = load_workflow(config.resolve_workflow_wan())
    job = apply_scene_to_workflow(
        wf,
        visual_prompt=visual,
        motion_prompt=motion,
        filename_prefix=prefix,
        width=ww,
        height=wh,
        reference_image_name=ref,
        node_map=config.NODE_MAP_WAN,
        include_motion_in_prompt=True,
        cinematic_suffix=config.STYLE_SUFFIX["live"],
        negative_prompt=neg,
        seed=seed,
    )
    job["21"]["inputs"].update({"length": length, "width": ww, "height": wh})
    # High-noise only → SaveLatent (no VAE decode / no low model)
    hi = job["22"]["inputs"]
    hi["steps"] = steps
    hi["cfg"] = cfg
    hi["start_at_step"] = 0
    hi["end_at_step"] = half
    hi["return_with_leftover_noise"] = "enable"
    hi["add_noise"] = "enable"
    # Drop low-noise path + video nodes; save latent instead
    for nid in ("14", "18", "23", "24", "25", "26"):
        job.pop(nid, None)
    job["90"] = {
        "class_type": "SaveLatent",
        "inputs": {"samples": ["22", 0], "filename_prefix": latent_prefix},
    }
    log.info("HIGH pass %s %sx%s len=%s steps=%s half=%s", prefix, ww, wh, length, steps, half)
    run_workflow(job, client_id=new_client_id(), timeout_s=5400)
    lat = _find_latent(prefix + "_hi", t0)
    if lat is None:
        # broader search
        lat = _find_latent(latent_prefix, t0)
    if lat is None:
        raise RuntimeError(f"SaveLatent produced no .latent for {prefix}")
    log.info("HIGH latent → %s (%.1f MB)", lat, lat.stat().st_size / 1e6)
    return lat


def run_low_pass(
    *,
    still: Path,
    latent_path: Path,
    visual: str,
    motion: str,
    prefix: str,
    seed: int,
    neg: str,
    ww: int,
    wh: int,
    length: int,
    steps: int,
    cfg: float,
    half: int,
    out_mp4: Path,
) -> Path:
    if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
        raise RuntimeError("Comfy restart before low-pass failed")
    latent_name = _stage_latent_for_load(latent_path)
    ref = _stage_still(still, f"{prefix}_{ww}x{wh}_low.png", (ww, wh))
    wf = load_workflow(config.resolve_workflow_wan())
    job = apply_scene_to_workflow(
        wf,
        visual_prompt=visual,
        motion_prompt=motion,
        filename_prefix=prefix,
        width=ww,
        height=wh,
        reference_image_name=ref,
        node_map=config.NODE_MAP_WAN,
        include_motion_in_prompt=True,
        cinematic_suffix=config.STYLE_SUFFIX["live"],
        negative_prompt=neg,
        seed=seed,
    )
    job["21"]["inputs"].update({"length": length, "width": ww, "height": wh})
    # Low-noise only: keep WanImageToVideo for I2V conditioning, but sample from saved latent.
    for nid in ("13", "17", "22"):
        job.pop(nid, None)
    job["91"] = {"class_type": "LoadLatent", "inputs": {"latent": latent_name}}
    lo = job["23"]["inputs"]
    lo["model"] = ["18", 0]
    lo["add_noise"] = "disable"
    lo["noise_seed"] = seed
    lo["steps"] = steps
    lo["cfg"] = cfg
    lo["positive"] = ["21", 0]
    lo["negative"] = ["21", 1]
    lo["latent_image"] = ["91", 0]
    lo["start_at_step"] = half
    lo["end_at_step"] = 10000
    lo["return_with_leftover_noise"] = "disable"
    job["24"]["inputs"]["samples"] = ["23", 0]
    job["26"]["inputs"]["filename_prefix"] = prefix
    log.info("LOW pass %s latent=%s steps=%s half=%s", prefix, latent_name, steps, half)
    _, paths = run_workflow(job, client_id=new_client_id(), timeout_s=5400)
    clip = pick_best_output(paths, prefix, allow_stale_disk=True)
    if not clip or not clip.exists():
        raise RuntimeError(f"LOW pass produced no video for {prefix}")
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(clip, out_mp4)
    log.info("LOW OK → %s (%.1f MB)", out_mp4, out_mp4.stat().st_size / 1e6)
    return out_mp4


def two_pass_wan(
    still: Path,
    *,
    visual: str,
    motion: str,
    prefix: str,
    seed: int,
    neg: str,
    out_mp4: Path,
    ww: int = 480,
    wh: int = 832,
    length: int = 49,
    steps: int = 10,
    cfg: float = 4.0,
) -> Path:
    half = max(2, steps // 2)
    lat = run_high_pass(
        still=still,
        visual=visual,
        motion=motion,
        prefix=prefix,
        seed=seed,
        neg=neg,
        ww=ww,
        wh=wh,
        length=length,
        steps=steps,
        cfg=cfg,
        half=half,
    )
    return run_low_pass(
        still=still,
        latent_path=lat,
        visual=visual,
        motion=motion,
        prefix=prefix,
        seed=seed,
        neg=neg,
        ww=ww,
        wh=wh,
        length=length,
        steps=steps,
        cfg=cfg,
        half=half,
        out_mp4=out_mp4,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    still = ROOT / "temp" / "romance_wan_premium_v3" / "dx_rom_wan_s00_still.png"
    out = ROOT / "temp" / "romance_wan_premium_v3" / "dx_smoke_twopass_v4.mp4"
    assert still.exists(), still
    two_pass_wan(
        still,
        visual="couple under umbrella rain soft blinks readable faces",
        motion="static hold soft blinks rain streaks",
        prefix="dx_smoke_twopass_v4",
        seed=99,
        neg=config.FLUX_NEGATIVE_PROMPT,
        out_mp4=out,
        ww=480,
        wh=832,
        length=49,
        steps=10,
        cfg=4.0,
    )
    print(f"SMOKE_OK {out}")


if __name__ == "__main__":
    main()
