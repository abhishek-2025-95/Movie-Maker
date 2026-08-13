"""HF Wan dinner-scene recipe: Flux still → Wan I2V HQ (12GB ladder).

Prompt structure from:
https://discuss.huggingface.co/t/how-to-get-the-most-out-of-prompts-for-wan-models/170354
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
)
from utils import restart_comfyui

log = logging.getLogger("wan_dinner")

# --- HF framework: cast → setting → camera → action → boundaries → style ---
CAST_SETTING = (
    "Exactly two people: one man and one woman in their 30s, sitting close together "
    "at the same dinner table. Warm, cozy restaurant interior at night, candlelight "
    "on the table, blurred background, no TV screens, no other people anywhere in the scene."
)
CAMERA = (
    "Static camera, eye-level, medium shot showing both of them from the waist up. "
    "The camera does not move, no zoom, no pan."
)
ACTION = (
    "The man keeps his arm gently around the woman's shoulders and they lean slightly "
    "toward each other. They talk quietly and smile. They sometimes nod and make small "
    "hand gestures, but they remain seated at the table the entire time. They do not "
    "stand up, they do not wave, and nobody ever enters or leaves the frame. They do "
    "not kiss, they simply talk and smile."
)
STYLE = (
    "Cinematic, realistic style, natural warm lighting, soft shallow depth of field, "
    "subtle film grain, realistic skin tones"
)

# Flux still = who/where/camera/style (posed for the opening beat)
FLUX_POSITIVE = f"{CAST_SETTING} {CAMERA} {STYLE}. They are seated, smiling softly, mid-conversation."
# Wan motion = action + boundaries (camera restated as positive constraints)
WAN_MOTION = f"{CAMERA} {ACTION} {STYLE}"
WAN_VISUAL = f"{CAST_SETTING} {CAMERA}"

NEGATIVE = (
    "third person, extra people, crowd, waiter entering, kiss, kissing, standing up, "
    "waving, walking away, camera zoom, pan, tilt, dolly, cut, jump cut, morphing faces, "
    "extra limbs, deformed hands, watermark, text, logo, blurry, mushy, oversmoothed"
)

OUT = ROOT / "final_outputs" / "wan_dinner_couple_9x16.mp4"
WORK = ROOT / "temp" / "wan_dinner"
TARGET_SEC = 6.0
WAN_SIZE_LADDER = [(576, 1024), (512, 896), (480, 832)]
WAN_LENGTH = 65
WAN_CFG = 4.0
SEED = 170354  # fixed while iterating prompts (HF guide)


def _ensure_comfy() -> None:
    import urllib.request

    try:
        urllib.request.urlopen(f"http://{config.COMFYUI_HOST}/system_stats", timeout=3)
        log.info("ComfyUI already up")
        return
    except Exception:
        pass
    log.info("Starting ComfyUI…")
    if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
        raise RuntimeError("Failed to start ComfyUI")


def _set_wan_params(wf: dict, *, length: int, cfg: float, w: int, h: int) -> None:
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        inputs = node.setdefault("inputs", {})
        if node.get("class_type") == "WanImageToVideo":
            inputs["length"] = int(length)
            inputs["width"] = int(w)
            inputs["height"] = int(h)
        if node.get("class_type") in {"KSampler", "KSamplerAdvanced"} and "cfg" in inputs:
            inputs["cfg"] = float(cfg)


def _bump_steps(wf: dict, steps: int = 14) -> None:
    half = max(4, steps // 2)
    for node in wf.values():
        if not isinstance(node, dict) or node.get("class_type") != "KSamplerAdvanced":
            continue
        inputs = node.setdefault("inputs", {})
        inputs["steps"] = steps
        if str(inputs.get("add_noise", "")).lower() == "enable":
            inputs["end_at_step"] = half
        elif str(inputs.get("add_noise", "")).lower() == "disable":
            inputs["start_at_step"] = half


def _stage(plate: Path, name: str, size: tuple[int, int]) -> str:
    from PIL import Image

    config.COMFYUI_INPUT.mkdir(parents=True, exist_ok=True)
    dest = config.COMFYUI_INPUT / name
    Image.open(plate).convert("RGB").resize(size, Image.LANCZOS).save(dest, format="PNG")
    return name


def _hq_export(src: Path, dest: Path, *, seconds: float) -> Path:
    import subprocess

    from moviepy.editor import VideoFileClip, concatenate_videoclips, vfx

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = WORK / "wan_hq1080.mp4"
    ow, oh = config.OUTPUT_SIZES["9:16"]
    vf = f"scale={ow}:{oh}:flags=lanczos,unsharp=5:5:0.85:5:5:0.0,eq=contrast=1.05:saturation=1.03"
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(src), "-vf", vf,
            "-c:v", "libx264", "-preset", "slow", "-crf", "15",
            "-pix_fmt", "yuv420p", "-an", str(tmp),
        ],
        check=True,
        capture_output=True,
    )
    clip = VideoFileClip(str(tmp)).without_audio()
    if clip.duration + 0.05 < seconds:
        # subtle ping-pong pad (held dinner beat)
        parts = [clip]
        cur = float(clip.duration)
        fwd = True
        while cur + 0.01 < seconds:
            parts.append(clip if fwd else clip.fx(vfx.time_mirror))
            cur += float(clip.duration)
            fwd = not fwd
        clip = concatenate_videoclips(parts, method="compose").subclip(0, seconds)
    elif clip.duration > seconds + 0.05:
        clip = clip.subclip(0, seconds)
    clip.write_videofile(
        str(dest),
        fps=24,
        codec="libx264",
        audio=False,
        bitrate="18000k",
        preset="slow",
        ffmpeg_params=["-pix_fmt", "yuv420p", "-crf", "15"],
        logger=None,
    )
    clip.close()
    return dest


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    WORK.mkdir(parents=True, exist_ok=True)
    _ensure_comfy()

    fw, fh = config.RATIO_SIZES["9:16"]
    prefix_still = "dx_wan_dinner_still"
    prefix_wan = "dx_wan_dinner_wan"

    # --- Flux still ---
    flux_wf = load_workflow(config.WORKFLOW_FLUX)
    flux_job = apply_scene_to_workflow(
        flux_wf,
        visual_prompt=FLUX_POSITIVE,
        motion_prompt="",
        filename_prefix=prefix_still,
        width=fw,
        height=fh,
        node_map=config.NODE_MAP_FLUX,
        include_motion_in_prompt=False,
        cinematic_suffix=STYLE,
        negative_prompt=NEGATIVE,
        seed=SEED,
    )
    log.info("Queuing Flux dinner still %sx%s seed=%s…", fw, fh, SEED)
    _, still_paths = run_workflow(flux_job, timeout_s=900)
    still = pick_best_output(still_paths, prefix_still)
    if not still or not still.exists():
        raise FileNotFoundError(f"Flux still missing for {prefix_still}")
    still_local = WORK / "still.png"
    shutil.copy2(still, still_local)
    log.info("Still OK → %s", still_local)

    # --- Wan I2V HQ ladder ---
    wan_out = WORK / "wan_raw.mp4"
    ok = None
    for ww, wh in WAN_SIZE_LADDER:
        log.info("VRAM reset before Wan @%sx%s…", ww, wh)
        if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
            raise RuntimeError("ComfyUI restart before Wan failed")
        ref = _stage(still_local, f"dinner_start_{ww}x{wh}.png", (ww, wh))
        wan_wf = load_workflow(config.WORKFLOW_WAN)
        wan_job = apply_scene_to_workflow(
            wan_wf,
            visual_prompt=WAN_VISUAL,
            motion_prompt=WAN_MOTION,
            filename_prefix=prefix_wan,
            width=ww,
            height=wh,
            reference_image_name=ref,
            node_map=config.NODE_MAP_WAN,
            include_motion_in_prompt=True,
            cinematic_suffix=STYLE,
            negative_prompt=NEGATIVE,
            seed=SEED,
        )
        _set_wan_params(wan_job, length=WAN_LENGTH, cfg=WAN_CFG, w=ww, h=wh)
        _bump_steps(wan_job, 14)
        log.info("Queuing Wan dinner length=%s cfg=%.1f %sx%s…", WAN_LENGTH, WAN_CFG, ww, wh)
        try:
            _, paths = run_workflow(wan_job, timeout_s=5400)
            clip = pick_best_output(paths, prefix_wan, allow_stale_disk=True)
        except Exception as exc:
            log.warning("Wan %sx%s failed: %s", ww, wh, exc)
            continue
        if clip and clip.exists():
            shutil.copy2(clip, wan_out)
            (WORK / "meta.txt").write_text(
                f"{ww}x{wh} length={WAN_LENGTH} cfg={WAN_CFG} seed={SEED}\n",
                encoding="utf-8",
            )
            ok = wan_out
            log.info("Wan OK %sx%s → %s", ww, wh, wan_out)
            break
    if not ok:
        raise RuntimeError("All Wan size attempts failed")

    _hq_export(ok, OUT, seconds=TARGET_SEC)
    log.info("DONE %s (%.1f MB)", OUT, OUT.stat().st_size / 1e6)
    print(f"DONE {OUT}")


if __name__ == "__main__":
    main()
