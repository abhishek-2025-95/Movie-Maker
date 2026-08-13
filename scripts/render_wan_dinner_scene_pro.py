"""Dinner scene PRO — match neo-noir reel quality bar.

Noir-bar targets:
- Readable face key light (no silhouette)
- Arm-around-shoulder locked in still + Wan
- Natural talk motion (no cheek-caress drift)
- ~15 Mbps export + soft restaurant audio bed
- No dead freeze pad — duration follows Wan motion
"""
from __future__ import annotations

import logging
import shutil
import sys
import wave
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

log = logging.getLogger("wan_dinner_pro")

CAST_SETTING = (
    "Exactly two people only: one man and one woman in their 30s, sitting close together "
    "at the same small dinner table. Completely empty cozy restaurant interior at night — "
    "no other customers, no waiters, no staff, no background patrons. "
    "Warm candlelight on the table PLUS a soft warm key light on both faces so skin tones "
    "are clearly readable — not silhouettes, not backlit-only. Soft bokeh lights only. "
    "No TV screens, no monitors, no phones on walls, no digital displays."
)
CAMERA = (
    "Static camera on a tripod, eye-level, medium shot showing both from the waist up. "
    "The camera does not move: no zoom, no pan, no tilt, no dolly, no push-in."
)
POSE_LOCK = (
    "They sit side-by-side / angled toward each other at the table, not nose-to-nose. "
    "Keep roughly a hand-width of clear air between their noses at all times. "
    "The man's arm stays gently around the woman's shoulders. "
    "His other hand rests on the table. Her hands stay on the table or near her own chin. "
    "He does NOT caress her cheek, does NOT hold her face, does NOT cup her jaw. "
    "They do NOT press foreheads together. They do NOT Eskimo-kiss / nose-touch."
)
ANTI_KISS = (
    "Medium talking distance — faces clearly separated, never intimate close-up. "
    "Lips stay apart. Foreheads never touch. Noses never touch. "
    "They do not lean in for a kiss. They only talk and smile across a small gap."
)
ACTION = (
    f"{POSE_LOCK} {ANTI_KISS} "
    "They remain on opposite sides of the table facing each other with clear space. "
    "They talk quietly: small mouth movements, soft smiles, tiny nods, occasional blinks. "
    "Candle flames flicker softly. They remain seated. Nobody enters or leaves the frame. "
    "Do not move their faces closer together over time."
)
STYLE = (
    "Cinematic photoreal, natural warm lighting, readable facial detail, "
    "soft shallow depth of field, subtle film grain, realistic skin tones, "
    "premium short-form film look"
)

FLUX_START = (
    f"{CAST_SETTING} {CAMERA} {STYLE}. "
    f"{POSE_LOCK} {ANTI_KISS} "
    "Both faces brightly lit with warm key light catching cheeks and eyes. "
    "Opening beat: smiling, mid-conversation, lips apart."
)

WAN_VISUAL = f"{CAST_SETTING} {CAMERA} {POSE_LOCK}"
WAN_MOTION = f"{CAMERA} {ACTION} {STYLE}"

NEGATIVE = (
    "kiss, kissing, lips touching, lip lock, makeout, forehead touch, forehead to forehead, "
    "noses touching, nose rub, eskimo kiss, almost kissing, leaning in to kiss, "
    "hand on cheek, caressing face, cupping jaw, holding her face, "
    "silhouette, backlit faces, underexposed faces, hidden face, "
    "third person, extra people, crowd, waiter, background patrons, "
    "TV, television, monitor, screen, smartphone on wall, "
    "camera zoom, pan, tilt, dolly, push-in, standing up, walking, waving, "
    "extra limbs, deformed hands, watermark, text, logo, blurry, mushy, oversmoothed, "
    "plastic skin, low resolution"
)

OUT = ROOT / "final_outputs" / "wan_dinner_couple_9x16.mp4"
WORK = ROOT / "temp" / "wan_dinner_pro"
WAN_SIZE_LADDER = [(576, 1024), (512, 896), (480, 832)]
WAN_LENGTH = 81  # ~5.0s @ 16fps — continuous motion, no freeze pad needed
WAN_CFG = 4.5
WAN_STEPS = 16
SEED = 27072719
BITRATE = getattr(config, "EXPORT_BITRATE", "15000k")


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


def _bump_steps(wf: dict, steps: int = 16) -> None:
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
    # Mild face lift on still so Wan inherits brighter faces
    img = Image.open(dest).convert("RGB")
    img = ImageEnhance.Brightness(img).enhance(1.08)
    img = ImageEnhance.Contrast(img).enhance(1.06)
    img.save(dest, format="PNG")
    return dest


def _face_detail_restore(frame: np.ndarray, sharp: Image.Image) -> np.ndarray:
    fr = Image.fromarray(frame).convert("RGB")
    sp = sharp.convert("RGB").resize(fr.size, Image.LANCZOS)
    blur = sp.filter(ImageFilter.GaussianBlur(2.0))
    sp_a = np.asarray(sp).astype(np.float32)
    bl_a = np.asarray(blur).astype(np.float32)
    detail = sp_a - bl_a
    h, w, _ = detail.shape
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    mask = np.exp(-((yy - 0.36) ** 2) / (2 * 0.13**2) - ((xx - 0.5) ** 2) / (2 * 0.30**2))
    mask = np.clip(mask * 1.4, 0, 1)[..., None]
    base = np.asarray(fr).astype(np.float32)
    # Gentle midtone lift on faces (noir-readable)
    lift = 1.0 + 0.12 * mask[..., 0:1]
    out = base * lift + detail * mask * 0.65
    return np.clip(out, 0, 255).astype(np.uint8)


def _restaurant_bed(duration: float, out_path: Path) -> Path:
    """Soft warm restaurant ambience — low murmur + room tone."""
    sr = 44100
    n = int(duration * sr)
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(42)
    room = 0.035 * rng.normal(0, 1, n)
    # Slow warm drone
    drone = (
        0.028 * np.sin(2 * np.pi * 65 * t)
        + 0.018 * np.sin(2 * np.pi * 98 * t)
        + 0.012 * np.sin(2 * np.pi * 130 * t)
    )
    # Distant murmur (filtered noise pulses)
    murmur = 0.022 * rng.normal(0, 1, n) * (0.55 + 0.45 * np.sin(2 * np.pi * 0.35 * t))
    # Soft high sparkle (glass/clink-ish sparse)
    sparkle = np.zeros(n)
    for at in (0.8, 2.1, 3.4, 4.6):
        i0 = int(at * sr)
        if i0 + 2000 < n:
            tt = np.arange(2000) / sr
            sparkle[i0 : i0 + 2000] += 0.04 * np.sin(2 * np.pi * 2400 * tt) * np.exp(-tt * 14)
    audio = room + drone + murmur + sparkle
    # Fade in/out
    fade = int(0.25 * sr)
    audio[:fade] *= np.linspace(0, 1, fade)
    audio[-fade:] *= np.linspace(1, 0, fade)
    peak = np.max(np.abs(audio)) + 1e-9
    audio = (0.55 * audio / peak).astype(np.float32)
    # Stereo write
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(audio * 32767, -32767, 32767).astype(np.int16)
    stereo = np.column_stack([pcm, pcm]).reshape(-1)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(stereo.tobytes())
    return out_path


def _hq_export(src: Path, dest: Path, *, start_still: Path) -> Path:
    """Noir-bar export: mild upscale, face restore/lift, 15Mbps, restaurant audio."""
    import subprocess

    from moviepy.editor import AudioFileClip, ImageSequenceClip, VideoFileClip

    dest.parent.mkdir(parents=True, exist_ok=True)
    ow, oh = config.OUTPUT_SIZES["9:16"]
    tmp = WORK / "wan_scaled.mp4"
    # Mild sharpen + slight gamma lift (faces out of mud)
    vf = (
        f"scale={ow}:{oh}:flags=lanczos,"
        f"eq=gamma=1.06:contrast=1.04:saturation=1.05,"
        f"unsharp=3:3:0.50:3:3:0.0"
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(src), "-vf", vf,
            "-c:v", "libx264", "-preset", "slow", "-b:v", BITRATE,
            "-pix_fmt", "yuv420p", "-an", str(tmp),
        ],
        check=True,
        capture_output=True,
    )

    start_img = Image.open(start_still).convert("RGB").resize((ow, oh), Image.LANCZOS)
    raw = VideoFileClip(str(tmp)).without_audio()
    fps = 24
    n = max(1, int(round(raw.duration * fps)))
    frames = []
    for i in range(n):
        t = min(raw.duration - 0.001, i / fps)
        frames.append(_face_detail_restore(raw.get_frame(t), start_img))
    dur = n / fps
    raw.close()

    clip = ImageSequenceClip(frames, fps=fps)
    bed = _restaurant_bed(dur + 0.15, WORK / "restaurant_bed.wav")
    audio = AudioFileClip(str(bed)).volumex(0.55).subclip(0, dur)
    clip = clip.set_audio(audio)
    clip.write_videofile(
        str(dest),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        bitrate=BITRATE,
        preset="slow",
        ffmpeg_params=["-pix_fmt", "yuv420p"],
        logger=None,
    )
    clip.close()
    audio.close()
    return dest


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    WORK.mkdir(parents=True, exist_ok=True)
    _ensure_comfy()

    # Prefer locked bright talking-distance plate when present (Flux often collapses to nose-touch).
    locked = WORK / "dx_dinner_pro_locked.png"
    if locked.exists():
        start_still = locked
        log.info("Using locked talking-distance still → %s", start_still)
    else:
        start_still = _flux_still(FLUX_START, "dx_dinner_pro_v2_start", SEED)
        log.info("Pro start still → %s", start_still)

    prefix_wan = "dx_dinner_pro_locked_wan"
    wan_out = WORK / "wan_raw.mp4"
    ok = None
    for ww, wh in WAN_SIZE_LADDER:
        log.info("VRAM reset before Wan @%sx%s…", ww, wh)
        if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
            raise RuntimeError("ComfyUI restart before Wan failed")
        ref = _stage(start_still, f"dinner_pro_start_{ww}x{wh}.png", (ww, wh))
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
        _bump_steps(wan_job, WAN_STEPS)
        log.info("Queuing Wan PRO length=%s cfg=%.1f steps=%s %sx%s…", WAN_LENGTH, WAN_CFG, WAN_STEPS, ww, wh)
        try:
            _, paths = run_workflow(wan_job, timeout_s=5400)
            clip = pick_best_output(paths, prefix_wan, allow_stale_disk=True)
        except Exception as exc:
            log.warning("Wan %sx%s failed: %s", ww, wh, exc)
            continue
        if clip and clip.exists():
            shutil.copy2(clip, wan_out)
            (WORK / "meta.txt").write_text(
                f"pro {ww}x{wh} length={WAN_LENGTH} cfg={WAN_CFG} steps={WAN_STEPS} seed={SEED}\n",
                encoding="utf-8",
            )
            ok = wan_out
            log.info("Wan OK %sx%s → %s", ww, wh, wan_out)
            break
    if not ok:
        raise RuntimeError("All Wan size attempts failed")

    _hq_export(ok, OUT, start_still=start_still)
    log.info("DONE %s (%.1f MB)", OUT, OUT.stat().st_size / 1e6)
    print(f"DONE {OUT}")


if __name__ == "__main__":
    main()
