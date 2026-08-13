"""Render bare diagnostic-void background plate: Flux → Wan → 9:16 ≤10s.

No text burn. Near-static pitch-black terminal / faint pulsing grid.
"""
from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from comfy_runner import (
    apply_scene_to_workflow,
    load_workflow,
    pick_best_output,
    run_workflow,
    stage_reference_image,
)
from utils import restart_comfyui

log = logging.getLogger("diagnostic_void")

POSITIVE = (
    "Pure pitch-black #000000 digital canvas. Extreme macro, clinical, sterile aesthetic. "
    "In the background, incredibly faint, low-opacity dark-grey diagnostic data grid lines "
    "slowly pulsing. A high-tech terminal void. Zero camera movement, absolutely static "
    "framing with only micro-movements in the grid. No bright lights, deep shadows, minimalist UI."
)

NEGATIVE = (
    "Daylight, bright lights, people, nature, landscapes, complex motion, high contrast, "
    "white background, water, cities, 3D objects, colorful, busy, text, letters, human face, "
    "organic textures, watermark, logo, UI panels, neon glow, lens flare, camera pan, zoom"
)

MOTION = (
    "absolutely static camera, locked framing, only extremely subtle micro pulse of faint "
    "dark-grey grid lines, atmospheric breathe, no pan, no zoom, no object motion"
)

OUT = ROOT / "final_outputs" / "diagnostic_void_9x16_10s.mp4"
TARGET_SEC = 10.0
# 12GB: CFG 7 OOM-kills mid-Wan; 4.0 + length 65 is the reliable sterile path
WAN_CFG = 4.0
WAN_LENGTH = 65  # ~4s @16fps — freeze-pad to 10s


def _set_wan_params(wf: dict, *, length: int, cfg: float, w: int, h: int) -> None:
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        inputs = node.setdefault("inputs", {})
        if node.get("class_type") == "WanImageToVideo":
            inputs["length"] = int(length)
            inputs["width"] = int(w)
            inputs["height"] = int(h)
        if node.get("class_type") in {"KSampler", "KSamplerAdvanced"}:
            if "cfg" in inputs:
                inputs["cfg"] = float(cfg)


def _ensure_comfy() -> None:
    import urllib.request

    try:
        urllib.request.urlopen(f"http://{config.COMFYUI_HOST}/system_stats", timeout=3)
        log.info("ComfyUI already up")
        return
    except Exception:
        pass
    log.info("Starting ComfyUI --lowvram…")
    if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
        raise RuntimeError("Failed to start ComfyUI")


def _freeze_pad_upscale(src: Path, dest: Path, *, seconds: float) -> Path:
    from moviepy.editor import VideoFileClip, concatenate_videoclips

    dest.parent.mkdir(parents=True, exist_ok=True)
    clip = VideoFileClip(str(src)).without_audio()
    ow, oh = config.OUTPUT_SIZES["9:16"]
    clip = clip.resize((ow, oh))
    if clip.duration + 0.05 < seconds:
        gap = seconds - float(clip.duration)
        hold = clip.to_ImageClip(t=max(0, float(clip.duration) - 0.04)).set_duration(gap)
        clip = concatenate_videoclips([clip, hold], method="compose")
    elif clip.duration > seconds + 0.05:
        clip = clip.subclip(0, seconds)
    clip.write_videofile(
        str(dest),
        fps=24,
        codec="libx264",
        audio=False,
        bitrate="12000k",
        preset="medium",
        threads=4,
        logger=None,
    )
    clip.close()
    return dest


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _ensure_comfy()

    fw, fh = config.RATIO_SIZES["9:16"]
    ww, wh = config.WAN_SIZES["9:16"]
    prefix_still = "dx_diagnostic_void_still"
    prefix_wan = "dx_diagnostic_void_wan"

    # --- Flux still ---
    flux_wf = load_workflow(config.WORKFLOW_FLUX)
    flux_job = apply_scene_to_workflow(
        flux_wf,
        visual_prompt=POSITIVE,
        motion_prompt="",
        filename_prefix=prefix_still,
        width=fw,
        height=fh,
        node_map=config.NODE_MAP_FLUX,
        include_motion_in_prompt=False,
        cinematic_suffix="clinical sterile digital void, pitch black, no text",
        negative_prompt=NEGATIVE,
    )
    # Slightly higher Flux guidance if graph has cfg
    for node in flux_job.values():
        if isinstance(node, dict) and node.get("class_type") == "KSampler":
            if "cfg" in node.get("inputs", {}):
                node["inputs"]["cfg"] = 3.5  # Flux usually ~3.5; keep stable
    log.info("Queuing Flux still %sx%s…", fw, fh)
    _, still_paths = run_workflow(flux_job, timeout_s=900)
    still = pick_best_output(still_paths, prefix_still)
    if not still or not still.exists():
        raise FileNotFoundError(f"Flux still missing for prefix {prefix_still}")
    staged = ROOT / "temp" / "diagnostic_void" / "still.png"
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(still, staged)
    log.info("Still OK → %s", still)

    # Hard VRAM reset before Wan (12GB lowvram — /free alone is not enough)
    log.info("Restarting ComfyUI before Wan…")
    if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
        raise RuntimeError("ComfyUI restart before Wan failed")

    ref_name = stage_reference_image(still, "diagnostic_void_start.png")

    wan_wf = load_workflow(config.WORKFLOW_WAN)
    wan_job = apply_scene_to_workflow(
        wan_wf,
        visual_prompt=POSITIVE,
        motion_prompt=MOTION,
        filename_prefix=prefix_wan,
        width=ww,
        height=wh,
        reference_image_name=ref_name,
        node_map=config.NODE_MAP_WAN,
        include_motion_in_prompt=True,
        cinematic_suffix="static locked camera, micro grid pulse only",
        negative_prompt=NEGATIVE,
    )
    _set_wan_params(wan_job, length=WAN_LENGTH, cfg=WAN_CFG, w=ww, h=wh)
    log.info("Queuing Wan I2V length=%s cfg=%.1f %sx%s…", WAN_LENGTH, WAN_CFG, ww, wh)
    try:
        _, wan_paths = run_workflow(wan_job, timeout_s=3600)
        clip = pick_best_output(wan_paths, prefix_wan, allow_stale_disk=True)
    except Exception as exc:
        log.warning("Wan failed (%s) — freeze-pad still only", exc)
        clip = None
    if not clip or not clip.exists():
        # Last resort: Ken-Burns-free static hold from Flux still
        log.warning("No Wan clip — exporting static still hold to %ss", TARGET_SEC)
        from moviepy.editor import ImageClip

        ow, oh = config.OUTPUT_SIZES["9:16"]
        OUT.parent.mkdir(parents=True, exist_ok=True)
        ImageClip(str(staged)).resize((ow, oh)).set_duration(TARGET_SEC).write_videofile(
            str(OUT),
            fps=24,
            codec="libx264",
            audio=False,
            bitrate="10000k",
            preset="medium",
            logger=None,
        )
        log.info("DONE (still-hold) %s", OUT)
        print(f"DONE {OUT}")
        return
    log.info("Wan OK → %s", clip)

    raw = staged.parent / "wan_raw.mp4"
    shutil.copy2(clip, raw)
    _freeze_pad_upscale(raw, OUT, seconds=TARGET_SEC)
    log.info("DONE %s (%.1f MB)", OUT, OUT.stat().st_size / 1e6)
    print(f"DONE {OUT}")


if __name__ == "__main__":
    main()
