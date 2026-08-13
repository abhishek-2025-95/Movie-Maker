"""Dinner scene v2 — highest-ROI prompt + export fixes.

Fixes vs v1:
1. Empty restaurant / no screens Flux still
2. Hard anti-kiss positive constraints (talking distance)
3. Soft FLF: end Flux still + blend last frames toward it
4. Sharper export (milder upscale + unsharp + face detail restore)
"""
from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

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

log = logging.getLogger("wan_dinner_v2")

CAST_SETTING = (
    "Exactly two people only: one man and one woman in their 30s, sitting close together "
    "at the same small dinner table. Completely empty cozy restaurant interior at night — "
    "no other customers, no waiters, no staff, no background patrons, no silhouettes of people. "
    "Candlelight on the table. Soft bokeh lights only. No TV screens, no monitors, no phones "
    "visible on walls, no digital displays anywhere."
)
CAMERA = (
    "Static camera, eye-level, medium shot showing both of them from the waist up. "
    "The camera does not move: no zoom, no pan, no tilt, no dolly."
)
ANTI_KISS = (
    "They keep a clear talking distance between their faces — several inches of space. "
    "Their lips stay apart and never touch. Their foreheads never touch. Their noses never touch. "
    "They do not lean in for a kiss. They do not kiss. They only talk and smile."
)
ACTION = (
    "The man keeps his arm gently around the woman's shoulders and they lean slightly "
    "toward each other while still maintaining talking distance. They talk quietly and smile. "
    "They sometimes nod and make small hand gestures, but they remain seated the entire time. "
    "They do not stand up, they do not wave, and nobody ever enters or leaves the frame. "
    f"{ANTI_KISS}"
)
STYLE = (
    "Cinematic, realistic style, natural warm lighting, soft shallow depth of field, "
    "subtle film grain, realistic skin tones, sharp facial detail"
)

FLUX_START = (
    f"{CAST_SETTING} {CAMERA} {STYLE}. "
    "Opening beat: they are smiling and talking with clear space between their faces, "
    "lips apart, not about to kiss. Empty dining room behind them."
)
FLUX_END = (
    f"{CAST_SETTING} {CAMERA} {STYLE}. "
    "Ending beat: same couple still seated, still smiling and talking, "
    "clear space between faces, lips clearly apart, arm still around shoulders, "
    "definitely not kissing. Empty dining room behind them."
)

WAN_VISUAL = f"{CAST_SETTING} {CAMERA}"
WAN_MOTION = f"{CAMERA} {ACTION} {STYLE}"

NEGATIVE = (
    "kiss, kissing, lips touching, lip lock, makeout, forehead touch, nose to nose, "
    "leaning in to kiss, almost kissing, third person, extra people, crowd, waiter, "
    "background patrons, TV, television, monitor, screen, smartphone on wall, "
    "camera zoom, pan, tilt, dolly, standing up, walking, waving, "
    "extra limbs, deformed hands, watermark, text, logo, blurry, mushy, oversmoothed"
)

OUT = ROOT / "final_outputs" / "wan_dinner_couple_9x16.mp4"
WORK = ROOT / "temp" / "wan_dinner_v2"
TARGET_SEC = 6.0
WAN_SIZE_LADDER = [(576, 1024), (512, 896), (480, 832)]
WAN_LENGTH = 65
WAN_CFG = 4.5  # stronger prompt adherence for anti-kiss
SEED = 1703542
# Soft FLF only when end still matches start composition.
# Mismatched Flux ends cause ghosting — keep 0 unless end is an edit of start.
END_BLEND_SEC = 0.0


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
    config.COMFYUI_INPUT.mkdir(parents=True, exist_ok=True)
    dest = config.COMFYUI_INPUT / name
    Image.open(plate).convert("RGB").resize(size, Image.LANCZOS).save(dest, format="PNG")
    return name


def _flux_still(prompt: str, prefix: str, seed: int) -> Path:
    fw, fh = config.RATIO_SIZES["9:16"]
    flux_wf = load_workflow(config.WORKFLOW_FLUX)
    job = apply_scene_to_workflow(
        flux_wf,
        visual_prompt=prompt,
        motion_prompt="",
        filename_prefix=prefix,
        width=fw,
        height=fh,
        node_map=config.NODE_MAP_FLUX,
        include_motion_in_prompt=False,
        cinematic_suffix=STYLE,
        negative_prompt=NEGATIVE,
        seed=seed,
    )
    log.info("Queuing Flux %s %sx%s seed=%s…", prefix, fw, fh, seed)
    _, paths = run_workflow(job, timeout_s=900)
    still = pick_best_output(paths, prefix, allow_stale_disk=True)
    if not still or not still.exists():
        # Fallback: newest Comfy output matching prefix
        cands = sorted(
            config.COMFYUI_OUTPUT.glob(f"{prefix}*.png"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        still = cands[0] if cands else None
    if not still or not still.exists():
        raise FileNotFoundError(prefix)
    dest = WORK / f"{prefix}.png"
    shutil.copy2(still, dest)
    return dest


def _face_detail_restore(frame: np.ndarray, sharp: Image.Image) -> np.ndarray:
    """Pull high-frequency face detail from Flux still into soft Wan frame."""
    fr = Image.fromarray(frame).convert("RGB")
    sp = sharp.convert("RGB").resize(fr.size, Image.LANCZOS)
    # High-pass from sharp still
    blur = sp.filter(ImageFilter.GaussianBlur(2.2))
    sp_a = np.asarray(sp).astype(np.float32)
    bl_a = np.asarray(blur).astype(np.float32)
    detail = sp_a - bl_a
    # Center upper body / faces band weight
    h, w, _ = detail.shape
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    # Faces roughly mid-upper center
    mask = np.exp(-((yy - 0.38) ** 2) / (2 * 0.12**2) - ((xx - 0.5) ** 2) / (2 * 0.28**2))
    mask = np.clip(mask * 1.35, 0, 1)[..., None]
    out = np.asarray(fr).astype(np.float32) + detail * mask * 0.55
    return np.clip(out, 0, 255).astype(np.uint8)


def _hq_export(src: Path, dest: Path, *, start_still: Path, end_still: Path, seconds: float) -> Path:
    """Milder upscale + face restore + soft FLF end blend."""
    import subprocess

    from moviepy.editor import ImageSequenceClip, VideoFileClip, concatenate_videoclips, vfx

    dest.parent.mkdir(parents=True, exist_ok=True)
    ow, oh = config.OUTPUT_SIZES["9:16"]
    # Milder: scale then light unsharp (avoid crunchy fake sharpen)
    tmp = WORK / "wan_scaled.mp4"
    vf = f"scale={ow}:{oh}:flags=lanczos,unsharp=3:3:0.55:3:3:0.0"
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(src), "-vf", vf,
            "-c:v", "libx264", "-preset", "slow", "-crf", "16",
            "-pix_fmt", "yuv420p", "-an", str(tmp),
        ],
        check=True,
        capture_output=True,
    )

    start_img = Image.open(start_still).convert("RGB").resize((ow, oh), Image.LANCZOS)
    end_img = Image.open(end_still).convert("RGB").resize((ow, oh), Image.LANCZOS)
    end_arr = np.asarray(end_img).astype(np.float32)

    raw = VideoFileClip(str(tmp)).without_audio()
    fps = 24
    n = max(1, int(raw.duration * fps))
    blend_n = 0 if END_BLEND_SEC <= 0 else max(2, int(END_BLEND_SEC * fps))
    frames = []
    for i in range(n):
        t = min(raw.duration - 0.001, i / fps)
        fr = _face_detail_restore(raw.get_frame(t), start_img)
        # Soft FLF: last frames pull toward non-kiss end still
        rem = n - 1 - i
        if rem < blend_n:
            # ease-in toward end still
            p = 1.0 - (rem / max(1, blend_n - 1))
            p = p * p * (3 - 2 * p)
            # stronger on upper face band, keep table from end lightly
            mixed = fr.astype(np.float32) * (1 - p * 0.85) + end_arr * (p * 0.85)
            fr = np.clip(mixed, 0, 255).astype(np.uint8)
        frames.append(fr)
    raw.close()

    clip = ImageSequenceClip(frames, fps=fps)
    if clip.duration + 0.05 < seconds:
        hold = clip.to_ImageClip(t=max(0.0, float(clip.duration) - 1.0 / fps))
        hold = hold.set_duration(seconds - float(clip.duration) + 0.05)
        clip = concatenate_videoclips([clip, hold], method="compose").subclip(0, seconds)
    elif clip.duration > seconds + 0.05:
        clip = clip.subclip(0, seconds)

    clip.write_videofile(
        str(dest),
        fps=fps,
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

    # 1) Start + end Flux stills (soft FLF anchors)
    start_still = WORK / "dx_dinner_v2_start.png"
    if start_still.exists():
        log.info("Reusing start still → %s", start_still)
    else:
        start_still = _flux_still(FLUX_START, "dx_dinner_v2_start", SEED)
        log.info("Start still → %s", start_still)
    # Soft FLF end must match start composition. Without native FLF2V / img2img,
    # lock end = start (non-kiss anchor). A second Flux T2I end drifts and ghosts.
    end_still = WORK / "dx_dinner_v2_end.png"
    shutil.copy2(start_still, end_still)
    log.info("End still locked to start composition (anti-ghost FLF) → %s", end_still)

    # 2) Wan from start still
    prefix_wan = "dx_dinner_v2_wan"
    wan_out = WORK / "wan_raw.mp4"
    ok = None
    for ww, wh in WAN_SIZE_LADDER:
        log.info("VRAM reset before Wan @%sx%s…", ww, wh)
        if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
            raise RuntimeError("ComfyUI restart before Wan failed")
        ref = _stage(start_still, f"dinner_v2_start_{ww}x{wh}.png", (ww, wh))
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
        log.info("Queuing Wan v2 length=%s cfg=%.1f %sx%s…", WAN_LENGTH, WAN_CFG, ww, wh)
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

    _hq_export(ok, OUT, start_still=start_still, end_still=end_still, seconds=TARGET_SEC)
    log.info("DONE %s (%.1f MB)", OUT, OUT.stat().st_size / 1e6)
    print(f"DONE {OUT}")


if __name__ == "__main__":
    main()
