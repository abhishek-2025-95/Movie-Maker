"""Refine analog-phone Reel — narrative beat + living polish.

Improvements:
- Beat A: readable 03:14 (no spoiler, no caption)
- Living handheld sway + OLED flicker (not dead Ken Burns only)
- Thin lock-screen typography (Segoe UI Light)
- Hard glitch @6.0s → 25:66
- Echo flicker after hit (second beat / rewatch hook)
- Caption delayed until after echo (sharper copy)
- Quieter pre-drone so hit lands harder
"""
from __future__ import annotations

import logging
import math
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils import build_analog_horror_bed

log = logging.getLogger("refine_analog")

STILL = Path(r"C:\ComfyUI\output\dx_POV_dark_minimalist_bedroom_nightstand_s_s00_still_00001_.png")
OUT = ROOT / "final_outputs" / "POV_dark_minimalist_bedroom_nightstand_s.mp4"
WORK = ROOT / "temp" / "analog_refine"
W, H = 1080, 1920
FPS = 24
DUR_A = 5.8
DUR_GLITCH = 0.42
DUR_REVEAL = 0.85  # bare 25:66 before echo
DUR_ECHO = 0.38  # second micro scare
DUR_B = 2.35  # caption hold
CAPTION = "That time isn't possible."

CLOCK_BOX = (442, 718, 678, 1240)


def _clock_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\segoeuil.ttf"),  # light — closest to iOS lock
        Path(r"C:\Windows\Fonts\segoeuisl.ttf"),
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
    ]
    for p in candidates:
        if p.exists():
            return ImageFont.truetype(str(p), size=size)
    return ImageFont.load_default()


def _caption_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
        ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf",
    ]
    for p in candidates:
        if p.exists():
            return ImageFont.truetype(str(p), size=size)
    return ImageFont.load_default()


def load_base() -> Image.Image:
    im = Image.open(STILL).convert("RGB").resize((W, H), Image.LANCZOS)
    im = ImageEnhance.Contrast(im).enhance(1.10)
    im = ImageEnhance.Sharpness(im).enhance(1.28)
    return im


def _screen_mask(rgb: Image.Image) -> Image.Image:
    arr = np.asarray(rgb)
    y0, y1, x0, x1 = 700, 1275, 415, 705
    roi = arr[y0:y1, x0:x1]
    lum = roi.astype(np.float32).mean(axis=2)
    r, b = roi[:, :, 0], roi[:, :, 2]
    glass = ((lum > 5) & (b.astype(np.int16) > r.astype(np.int16) + 5)) | (lum > 90)
    m = Image.fromarray((glass.astype(np.uint8) * 255), mode="L")
    m = m.filter(ImageFilter.MaxFilter(21)).filter(ImageFilter.MinFilter(15))
    m = m.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(1.5))
    full = Image.new("L", (W, H), 0)
    full.paste(m, (x0, y0))
    guarantee = Image.new("L", (W, H), 0)
    ImageDraw.Draw(guarantee).rounded_rectangle(list(CLOCK_BOX), radius=56, fill=255)
    fu = np.maximum(np.asarray(full), np.asarray(guarantee))
    clip = Image.new("L", (W, H), 0)
    ImageDraw.Draw(clip).rounded_rectangle([428, 700, 692, 1265], radius=62, fill=255)
    out = np.minimum(fu, np.asarray(clip))
    return Image.fromarray(out, mode="L").point(lambda p: 255 if p > 60 else 0)


def _kill_digit_glow(rgb: Image.Image) -> Image.Image:
    arr = np.asarray(rgb).copy()
    mask = _screen_mask(rgb)
    m = np.asarray(mask) > 0
    if not m.any():
        return rgb
    roi = arr[m]
    lum = roi.astype(np.float32).mean(axis=1)
    dark = lum < 55
    fill = np.median(roi[dark], axis=0).astype(np.uint8) if dark.any() else np.array([8, 38, 65], np.uint8)
    bright = (arr.astype(np.float32).mean(axis=2) > 65) & m
    bm = Image.fromarray((bright.astype(np.uint8) * 255), mode="L")
    bm = bm.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(2.5))
    w = (np.asarray(bm).astype(np.float32) / 255.0)[..., None]
    w = w * m[..., None].astype(np.float32)
    arr = (arr.astype(np.float32) * (1.0 - w) + fill.astype(np.float32) * w).astype(np.uint8)
    return Image.fromarray(arr)


def _glass_plate(size: tuple[int, int], screen_mask: Image.Image) -> Image.Image:
    w, h = size
    ys, xs = np.where(np.asarray(screen_mask) > 0)
    if len(xs) == 0:
        return Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    top = np.array([4, 22, 40], dtype=np.float32)
    mid = np.array([12, 52, 84], dtype=np.float32)
    bot = np.array([7, 32, 58], dtype=np.float32)
    grad = np.zeros((bh, bw, 3), dtype=np.float32)
    for y in range(bh):
        t = y / max(1, bh - 1)
        c = top + (mid - top) * (t / 0.4) if t < 0.4 else mid + (bot - mid) * ((t - 0.4) / 0.6)
        grad[y, :] = c
    soft = Image.fromarray(np.clip(grad, 0, 255).astype(np.uint8), mode="RGB").filter(
        ImageFilter.GaussianBlur(2.0)
    )
    plate = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    plate.paste(soft.convert("RGBA"), (x0, y0))
    alpha = screen_mask.filter(ImageFilter.GaussianBlur(0.8))
    plate.putalpha(alpha)
    return plate


def paint_clock(base: Image.Image, time_str: str) -> Image.Image:
    """Full-glass lock-screen remake + thin iOS-like HH:MM."""
    mask = _screen_mask(base)
    cleaned = _kill_digit_glow(base.copy())
    im = cleaned.convert("RGBA")
    ys, xs = np.where(np.asarray(mask) > 0)
    cx = int((xs.min() + xs.max()) / 2) if len(xs) else W // 2
    y0 = int(ys.min()) if len(ys) else 720
    y1 = int(ys.max()) if len(ys) else 1240
    # Lock-screen time sits high on glass
    cy = y0 + int((y1 - y0) * 0.28)

    im = Image.alpha_composite(im, _glass_plate((W, H), mask))

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _clock_font(58)
    bbox = draw.textbbox((0, 0), time_str, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx, ty = cx - tw // 2, cy - th // 2
    # Soft OLED bloom (very light — avoids sticker look)
    bloom = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bloom)
    bd.text((tx, ty), time_str, font=font, fill=(200, 230, 255, 70))
    bloom = bloom.filter(ImageFilter.GaussianBlur(6))
    im = Image.alpha_composite(im, bloom)
    # Crisp glyph
    draw.text((tx, ty), time_str, font=font, fill=(236, 244, 255, 245))
    im = Image.alpha_composite(im, layer)
    out = im.convert("RGB")
    g = np.asarray(out).astype(np.int16)
    noise = np.random.default_rng(7).integers(-4, 5, g.shape, dtype=np.int16)
    return Image.fromarray(np.clip(g + noise, 0, 255).astype(np.uint8))


def paint_caption(im: Image.Image, alpha: float = 1.0) -> Image.Image:
    """Single-line delayed caption; alpha for fade-in."""
    a = max(0.0, min(1.0, float(alpha)))
    if a <= 0.01:
        return im.copy()
    out = im.convert("RGBA")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _caption_font(46)
    text = CAPTION
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (W - tw) // 2
    y = int(H * 0.11)
    oa = int(255 * a)
    for ox in range(-3, 4):
        for oy in range(-3, 4):
            if ox == 0 and oy == 0:
                continue
            draw.text((x + ox, y + oy), text, font=font, fill=(0, 0, 0, oa))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, oa))
    out = Image.alpha_composite(out, layer)
    return out.convert("RGB")


def punch_in(img: Image.Image, z: float = 1.08) -> Image.Image:
    z = max(1.0, float(z))
    nw, nh = int(W * z), int(H * z)
    pil = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - W) // 2
    top = max(0, (nh - H) // 2 + int(H * 0.01))
    if top + H > nh:
        top = nh - H
    return pil.crop((left, top, left + W, top + H))


def living_push(
    img: Image.Image,
    duration: float,
    *,
    zoom_start: float = 1.0,
    zoom_end: float = 1.05,
    sway_px: float = 7.0,
    flicker: float = 0.018,
    seed: int = 11,
):
    """Ken Burns + handheld sway + subtle OLED brightness breathe."""
    from moviepy.editor import ImageClip

    duration = max(0.1, float(duration))
    base = ImageClip(np.asarray(img)).set_duration(duration)
    z0, z1 = float(zoom_start), float(zoom_end)
    rng = np.random.default_rng(seed)

    def _live(get_frame, t):
        frame = get_frame(t)
        pil = Image.fromarray(frame)
        prog = min(1.0, max(0.0, float(t) / duration))
        z = z0 + (z1 - z0) * prog
        # Slow figure-8 handheld
        sx = sway_px * math.sin(2 * math.pi * (0.11 + 0.02 * seed % 3) * t)
        sy = sway_px * 0.65 * math.sin(2 * math.pi * 0.09 * t + 1.1)
        pad = int(max(abs(sx), abs(sy)) + 4)
        nw, nh = max(W + 2 * pad, int(W * z) + 2 * pad), max(H + 2 * pad, int(H * z) + 2 * pad)
        pil = pil.resize((nw, nh), Image.LANCZOS)
        cx = nw // 2 + int(sx)
        cy = nh // 2 + int(sy)
        left = max(0, min(nw - W, cx - W // 2))
        top = max(0, min(nh - H, cy - H // 2))
        pil = pil.crop((left, top, left + W, top + H))
        arr = np.asarray(pil).astype(np.float32)
        # Micro flicker (room / OLED breathe)
        breathe = 1.0 + flicker * math.sin(2 * math.pi * 0.35 * t)
        breathe += float(rng.normal(0, flicker * 0.25))
        arr = np.clip(arr * breathe, 0, 255).astype(np.uint8)
        return arr

    return base.fl(_live).set_duration(duration)


def glitch_burst(img_a: Image.Image, img_b: Image.Image, duration: float = DUR_GLITCH):
    from moviepy.editor import ImageSequenceClip

    n = max(4, int(duration * FPS))
    frames = []
    a = np.asarray(img_a)
    b = np.asarray(img_b)
    rng = np.random.default_rng(25)
    for i in range(n):
        mix = i / max(1, n - 1)
        base = a if (i % 2 == 0 and mix < 0.5) else b
        fr = base.copy().astype(np.int16)
        shift = int(8 + mix * 36)
        fr[:, :, 0] = np.roll(fr[:, :, 0], shift, axis=1)
        fr[:, :, 2] = np.roll(fr[:, :, 2], -shift, axis=1)
        for _ in range(3):
            y0 = int(rng.integers(350, 1500))
            h = int(rng.integers(18, 90))
            fr[y0 : y0 + h] = np.roll(fr[y0 : y0 + h], int(rng.integers(-70, 70)), axis=1)
        noise = rng.integers(-35, 45, fr.shape, dtype=np.int16)
        fr = np.clip(fr + noise, 0, 255).astype(np.uint8)
        if i % 2 == 1:
            pil = Image.fromarray(fr)
            d = ImageDraw.Draw(pil)
            f = _clock_font(72)
            junk = rng.choice(["88:88", "25:14", "03:66", "99:99", "25:66", "--:--"])
            bbox = d.textbbox((0, 0), junk, font=f)
            tw = bbox[2] - bbox[0]
            d.text(((W - tw) // 2, 860), junk, font=f, fill=(255, 255, 255))
            fr = np.asarray(pil)
        frames.append(fr)
    return ImageSequenceClip(frames, fps=FPS)


def echo_flicker(img_b: Image.Image, img_a: Image.Image, duration: float = DUR_ECHO):
    """Second beat: 25:66 blinks / flashes normal time once — rewatch hook."""
    from moviepy.editor import ImageSequenceClip

    n = max(3, int(duration * FPS))
    b = np.asarray(img_b)
    a = np.asarray(img_a)
    frames = []
    for i in range(n):
        if i in {1, 2}:
            fr = a.copy() if i == 1 else b.copy()
            if i == 1:
                fr = (fr.astype(np.int16) * 0.35).astype(np.uint8)
            fr = fr.astype(np.int16)
            fr[:, :, 0] = np.roll(fr[:, :, 0], 10, axis=1)
            fr[:, :, 2] = np.roll(fr[:, :, 2], -8, axis=1)
            fr = np.clip(fr, 0, 255).astype(np.uint8)
        else:
            fr = b.copy()
        frames.append(fr)
    return ImageSequenceClip(frames, fps=FPS)


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


# HuggingFace Wan prompting framework:
# cast/count → setting → camera → action timeline → motion boundaries → style
# https://discuss.huggingface.co/t/how-to-get-the-most-out-of-prompts-for-wan-models/170354
WAN_VISUAL = (
    "Exactly zero people and zero faces: only one black smartphone standing upright "
    "on a wooden nightstand in a dark minimalist bedroom at night. "
    "Cool blue practical lamp light from the right, soft shadows, shallow depth of field. "
    "The phone lock screen shows a single clean digital clock. "
    "No other objects enter the frame. No hands. No reflections of people."
)
WAN_MOTION_A = (
    "Static tripod camera, eye-level medium close-up on the phone and nightstand. "
    "The camera does not move: no zoom, no pan, no tilt, no dolly, no push-in. "
    "The phone and nightstand remain completely still in place the entire time. "
    "Only allowed motion: very subtle ambient light flicker, tiny slow dust motes in the air, "
    "and a soft OLED brightness breathe on the phone glass. "
    "The clock digits do not change, do not morph, and do not scramble. "
    "Nobody ever enters or leaves the frame. "
    "Cinematic photoreal night mood, natural micro atmosphere, sharp wood grain, subtle film grain."
)
WAN_MOTION_B = (
    "Static tripod camera, eye-level medium close-up on the phone and nightstand. "
    "The camera does not move: no zoom, no pan, no tilt, no dolly, no push-in. "
    "The phone and nightstand remain completely still in place the entire time. "
    "Only allowed motion: colder uneasy blue light shift, tiny dust motes, "
    "and a soft wrong-hour OLED flicker on the phone glass. "
    "The clock digits stay locked on the impossible time and do not morph into other numbers. "
    "Nobody ever enters or leaves the frame. "
    "Cinematic photoreal liminal horror mood, sharp detail, subtle film grain."
)
WAN_NEG = (
    "person, people, face, hand, finger, entering frame, extra objects, "
    "camera zoom, dolly, pan, tilt, handheld shake, warp, morphing digits, "
    "changing time, scrambled text, watermark, blur, mushy, oversmoothed, "
    "plastic look, low resolution, jpeg artifacts, cartoon"
)
# Highest quality ladder on 12GB (try → fallback). Length 65 ≈4s @16fps.
WAN_SIZE_LADDER = [(576, 1024), (512, 896), (480, 832)]
WAN_LENGTH = 65
WAN_CFG = 4.0  # >1 so negatives matter; still image-faithful for I2V
WAN_SEED_A = 31414
WAN_SEED_B = 25666


def _ensure_comfy() -> None:
    import urllib.request

    import config
    from utils import restart_comfyui

    try:
        urllib.request.urlopen(f"http://{config.COMFYUI_HOST}/system_stats", timeout=3)
        log.info("ComfyUI already up")
        return
    except Exception:
        pass
    log.info("Starting ComfyUI…")
    if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
        raise RuntimeError("Failed to start ComfyUI")


def _stage_plate(plate: Path, dest_name: str, size: tuple[int, int]) -> str:
    import config

    config.COMFYUI_INPUT.mkdir(parents=True, exist_ok=True)
    dest = config.COMFYUI_INPUT / dest_name
    Image.open(plate).convert("RGB").resize(size, Image.LANCZOS).save(dest, format="PNG")
    return dest_name


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


def run_wan_on_plate(
    plate: Path,
    *,
    prefix: str,
    motion: str,
    seed: int,
    visual: str = WAN_VISUAL,
) -> Path | None:
    """Highest-quality Wan I2V: HF-style constrained prompt + fixed seed + size ladder."""
    import config
    from comfy_runner import (
        apply_scene_to_workflow,
        load_workflow,
        pick_best_output,
        run_workflow,
    )
    from utils import restart_comfyui

    dest = WORK / f"{prefix}.mp4"
    for ww, wh in WAN_SIZE_LADDER:
        _ensure_comfy()
        log.info("VRAM reset before Wan %s @%sx%s seed=%s…", prefix, ww, wh, seed)
        if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
            raise RuntimeError("ComfyUI restart before Wan failed")

        ref = _stage_plate(plate, f"{prefix}_{ww}x{wh}_start.png", (ww, wh))
        wan_wf = load_workflow(config.WORKFLOW_WAN)
        job = apply_scene_to_workflow(
            wan_wf,
            visual_prompt=visual,
            motion_prompt=motion,
            filename_prefix=prefix,
            width=ww,
            height=wh,
            reference_image_name=ref,
            node_map=config.NODE_MAP_WAN,
            include_motion_in_prompt=True,
            cinematic_suffix="photoreal",
            negative_prompt=WAN_NEG,
            seed=int(seed),
        )
        _set_wan_params(job, length=WAN_LENGTH, cfg=WAN_CFG, w=ww, h=wh)
        _bump_steps(job, 14)
        log.info(
            "Queuing Wan HQ %s length=%s cfg=%.1f %sx%s seed=%s…",
            prefix, WAN_LENGTH, WAN_CFG, ww, wh, seed,
        )
        try:
            _, paths = run_workflow(job, timeout_s=5400)
            clip = pick_best_output(paths, prefix, allow_stale_disk=True)
        except Exception as exc:
            log.warning("Wan %sx%s failed (%s) — trying next size", ww, wh, exc)
            continue
        if not clip or not clip.exists():
            log.warning("Wan %sx%s produced no clip — trying next size", ww, wh)
            continue
        shutil.copy2(clip, dest)
        meta = WORK / f"{prefix}_meta.txt"
        meta.write_text(
            f"{ww}x{wh} length={WAN_LENGTH} cfg={WAN_CFG} seed={seed}\n",
            encoding="utf-8",
        )
        log.info("Wan HQ OK %sx%s → %s", ww, wh, dest)
        return dest
    return None


def hq_upscale_mp4(src: Path, dest: Path) -> Path:
    """Lanczos → 1080×1920 + strong unsharp (best OSS upscale without ESRGAN weights)."""
    import subprocess

    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={W}:{H}:flags=lanczos,"
        "unsharp=5:5:1.0:5:5:0.0,"
        "eq=contrast=1.06:saturation=1.04"
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(src),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "slow", "-crf", "15",
            "-pix_fmt", "yuv420p", "-an", str(dest),
        ],
        check=True,
        capture_output=True,
    )
    return dest


def restore_sharp_phone(frame: np.ndarray, sharp_plate: Image.Image, mask: Image.Image) -> np.ndarray:
    """Keep Wan room motion; restore sharp Flux phone glass + digits (kills mushy screen)."""
    fr = Image.fromarray(frame).convert("RGBA")
    plate = sharp_plate.convert("RGBA")
    # Soft mask: full restore on glass, feather into bezel
    m = mask.filter(ImageFilter.GaussianBlur(1.2))
    # Slightly contract so we don't paint outside phone
    m = m.point(lambda p: 255 if p > 90 else 0)
    m = m.filter(ImageFilter.GaussianBlur(1.5))
    overlay = plate.copy()
    overlay.putalpha(m)
    out = Image.alpha_composite(fr, overlay)
    return np.asarray(out.convert("RGB"))


def load_wan_clip_hq(path: Path, duration: float, sharp_plate: Image.Image, base_for_mask: Image.Image):
    """HQ upscale + sharp phone restore + ping-pong pad."""
    from moviepy.editor import VideoFileClip, concatenate_videoclips, vfx, ImageSequenceClip

    up = WORK / f"{path.stem}_hq1080.mp4"
    hq_upscale_mp4(path, up)
    mask = _screen_mask(base_for_mask)
    raw = VideoFileClip(str(up)).without_audio()

    # Bake restored frames (preserves sharpness through assemble)
    n = int(raw.duration * FPS) + 1
    frames = []
    for i in range(n):
        t = min(raw.duration - 0.001, i / FPS)
        fr = restore_sharp_phone(raw.get_frame(t), sharp_plate, mask)
        frames.append(fr)
    raw.close()
    clip = ImageSequenceClip(frames, fps=FPS)

    if clip.duration + 0.05 >= duration:
        return clip.subclip(0, duration)
    parts = [clip]
    cur = float(clip.duration)
    fwd = True
    while cur + 0.01 < duration:
        seg = clip if fwd else clip.fx(vfx.time_mirror)
        parts.append(seg)
        cur += float(clip.duration)
        fwd = not fwd
    return concatenate_videoclips(parts, method="compose").subclip(0, duration)


def burn_caption_on_clip(clip, caption_img: Image.Image, *, fade_in: float = 0.55):
    """Fade in caption text only (no full-band plate blend seam)."""
    # Build transparent text layer from caption plate vs bare difference is fragile;
    # redraw crisp text overlay instead.
    text_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_layer)
    font = _caption_font(46)
    text = CAPTION
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (W - tw) // 2
    y = int(H * 0.11)
    for ox in range(-3, 4):
        for oy in range(-3, 4):
            if ox == 0 and oy == 0:
                continue
            draw.text((x + ox, y + oy), text, font=font, fill=(0, 0, 0, 255))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    tl = np.asarray(text_layer).astype(np.float32)

    def _overlay(get_frame, t):
        fr = get_frame(t).astype(np.float32)
        prog = min(1.0, max(0.0, float(t) / max(0.05, fade_in)))
        prog = prog * prog * (3 - 2 * prog)
        a = (tl[:, :, 3:4] / 255.0) * prog
        rgb = tl[:, :, :3]
        mixed = fr * (1.0 - a) + rgb * a
        return np.clip(mixed, 0, 255).astype(np.uint8)

    return clip.fl(_overlay)


def self_qc(path: Path) -> None:
    import subprocess

    qc = WORK / "qc"
    qc.mkdir(parents=True, exist_ok=True)
    checks = [
        (1.2, "pre"),
        (4.5, "pre2"),
        (5.95, "glitch"),
        (6.8, "reveal"),
        (7.3, "echo"),
        (8.5, "post"),
    ]
    for t, tag in checks:
        p = qc / f"{tag}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(t), "-i", str(path), "-frames:v", "1", "-update", "1", str(p)],
            check=True,
            capture_output=True,
        )
        log.info("QC frame %s @%.2fs → %s", tag, t, p)


def main(assemble_only: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    WORK.mkdir(parents=True, exist_ok=True)
    if not STILL.exists():
        raise FileNotFoundError(STILL)

    base = load_base()
    # Mild punch-in only on still plates (composition), then Wan does real motion — no Ken Burns zoom
    plate_a = punch_in(paint_clock(base, "03:14"), 1.06)
    plate_b_raw = paint_clock(base, "25:66")
    pb = np.asarray(plate_b_raw).astype(np.int16)
    pb[:, :, 0] = np.clip(pb[:, :, 0] - 10, 0, 255)
    pb[:, :, 2] = np.clip(pb[:, :, 2] + 12, 0, 255)
    tinted = Image.fromarray(pb.astype(np.uint8))
    plate_b_bare = punch_in(tinted, 1.06)
    plate_b_cap = punch_in(paint_caption(tinted, alpha=1.0), 1.06)
    plate_a_path = WORK / "plate_a_0314.png"
    plate_b_path = WORK / "plate_b_2566.png"
    plate_a.save(plate_a_path)
    plate_b_bare.save(plate_b_path)
    plate_b_cap.save(WORK / "plate_b_caption.png")

    from moviepy.editor import AudioFileClip, concatenate_videoclips

    # --- Highest-quality Wan ladder + sharp phone restore ---
    wan_a = WORK / "dx_analog_wan_hq_a.mp4"
    wan_b = WORK / "dx_analog_wan_hq_b.mp4"
    if not assemble_only:
        wan_a = run_wan_on_plate(
            plate_a_path,
            prefix="dx_analog_wan_hq_a",
            motion=WAN_MOTION_A,
            seed=WAN_SEED_A,
        ) or wan_a
        wan_b = run_wan_on_plate(
            plate_b_path,
            prefix="dx_analog_wan_hq_b",
            motion=WAN_MOTION_B,
            seed=WAN_SEED_B,
        ) or wan_b
    wan_a = wan_a if isinstance(wan_a, Path) and wan_a.exists() else None
    wan_b = wan_b if isinstance(wan_b, Path) and wan_b.exists() else None

    post_dur = DUR_REVEAL + DUR_ECHO + DUR_B
    if wan_a and wan_b:
        log.info("Assembling Wan HQ (native ladder + sharp phone restore)")
        clip_a = load_wan_clip_hq(wan_a, DUR_A, plate_a, plate_a)
        fa = Image.fromarray(clip_a.get_frame(max(0, float(clip_a.duration) - 0.05)))
        clip_b_full = load_wan_clip_hq(wan_b, post_dur, plate_b_bare, plate_b_bare)
        fb0 = Image.fromarray(clip_b_full.get_frame(0.05))
        clip_g = glitch_burst(fa, fb0, DUR_GLITCH)
        clip_reveal = clip_b_full.subclip(0.0, DUR_REVEAL)
        fe = Image.fromarray(clip_b_full.get_frame(DUR_REVEAL))
        clip_echo = echo_flicker(fe, fa, DUR_ECHO)
        rest = clip_b_full.subclip(DUR_REVEAL + DUR_ECHO, post_dur)
        clip_hold = burn_caption_on_clip(rest, plate_b_cap, fade_in=0.55)
        video = concatenate_videoclips(
            [clip_a, clip_g, clip_reveal, clip_echo, clip_hold],
            method="compose",
        )
    else:
        log.warning("Wan HQ unavailable — fallback WITHOUT zoom (static + micro flicker only)")
        clip_a = living_push(plate_a, DUR_A, zoom_start=1.0, zoom_end=1.0, sway_px=3.0, seed=3)
        clip_g = glitch_burst(plate_a, plate_b_bare, DUR_GLITCH)
        clip_reveal = living_push(plate_b_bare, DUR_REVEAL, zoom_start=1.0, zoom_end=1.0, sway_px=2.0, seed=9)
        clip_echo = echo_flicker(plate_b_bare, plate_a, DUR_ECHO)
        clip_hold = living_push(plate_b_cap, DUR_B, zoom_start=1.0, zoom_end=1.0, sway_px=2.0, seed=17)
        video = concatenate_videoclips(
            [clip_a, clip_g, clip_reveal, clip_echo, clip_hold],
            method="compose",
        )

    bed = WORK / "bed.wav"
    echo_at = DUR_A + DUR_GLITCH + DUR_REVEAL
    build_analog_horror_bed(
        float(video.duration),
        glitch_at=DUR_A,
        out_path=bed,
        loop_end_silence=0.4,
        pre_glitch_gain=0.34,
        post_glitch_gain=0.8,
    )
    import wave

    with wave.open(str(bed), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
    audio_i = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    if ch == 2:
        audio_i = audio_i.reshape(-1, 2).mean(axis=1)
    g0 = int(echo_at * sr)
    thud_n = int(0.12 * sr)
    if g0 + thud_n < len(audio_i):
        tt = np.arange(thud_n) / sr
        thud = 0.28 * 32767 * np.sin(2 * np.pi * 48 * tt) * np.exp(-tt * 22)
        audio_i[g0 : g0 + thud_n] += thud
    audio_i = np.clip(audio_i, -32767, 32767).astype(np.int16)
    with wave.open(str(bed), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_i.tobytes())

    audio = AudioFileClip(str(bed))
    video = video.set_audio(audio)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = WORK / "refined.mp4"
    video.write_videofile(
        str(tmp_out),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="20000k",
        audio_bitrate="192k",
        preset="slow",
        threads=4,
        ffmpeg_params=["-pix_fmt", "yuv420p", "-crf", "14"],
        logger=None,
    )
    video.close()
    audio.close()
    shutil.copy2(tmp_out, OUT)
    self_qc(OUT)
    log.info("DONE %s (%.1f MB)", OUT, OUT.stat().st_size / 1e6)
    print(f"DONE {OUT}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--assemble-only", action="store_true", help="Reuse existing Wan HQ clips")
    args = ap.parse_args()
    main(assemble_only=bool(args.assemble_only))
