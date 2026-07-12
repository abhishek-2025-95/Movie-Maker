"""Programmatic assembly: concat clips, voice, optional BGM + CapCut-style captions."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

# Pillow>=10 removed Image.ANTIALIAS; MoviePy 1.0.3 still references it.
from PIL import Image, ImageDraw, ImageFont, ImageFilter

if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS  # type: ignore[attr-defined]

import config

log = logging.getLogger(__name__)


def _first_bgm() -> Path | None:
    if not config.BGM_DIR.exists():
        return None
    for ext in ("*.mp3", "*.wav", "*.m4a"):
        files = sorted(config.BGM_DIR.glob(ext))
        if files:
            return files[0]
    return None


def _load_font(size: int = 65) -> ImageFont.ImageFont:
    candidates = [
        str(config.ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf"),
        r"C:\Windows\Fonts\impact.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\NirmalaB.ttf",
        r"C:\Windows\Fonts\Nirmala.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=8)
    return bbox[2] - bbox[0]


def wrap_caption_by_pixels(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.ImageFont,
    max_width_px: int,
    max_lines: int = 3,
) -> str:
    """Word-boundary wrap to a pixel width — never cuts mid-word."""
    words = text.strip().replace("\n", " ").split()
    if not words:
        return ""

    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join(current + [word])
        if _text_width(draw, trial, font) <= max_width_px or not current:
            current.append(word)
            continue
        lines.append(" ".join(current))
        current = [word]
        if len(lines) >= max_lines:
            current = []
            break
    if current and len(lines) < max_lines:
        lines.append(" ".join(current))
    return "\n".join(lines)


def _fit_caption(
    text: str,
    draw: ImageDraw.ImageDraw,
    max_box_w: int,
) -> tuple[str, ImageFont.ImageFont]:
    raw = text.strip()
    for size in (70, 65, 58, 52, 46, 40):
        font = _load_font(size)
        wrapped = wrap_caption_by_pixels(raw, draw, font, max_box_w, max_lines=3)
        kept = len(wrapped.replace("\n", " ").split())
        if kept >= len(raw.split()):
            return wrapped, font
    font = _load_font(40)
    return wrap_caption_by_pixels(raw, draw, font, max_box_w, max_lines=4), font


def _parse_color(name: str) -> tuple[int, int, int, int]:
    table = {
        "yellow": (255, 230, 0, 255),
        "white": (255, 255, 255, 255),
        "black": (0, 0, 0, 255),
    }
    return table.get((name or "yellow").lower(), (255, 230, 0, 255))


def _caption_overlay_clip(text: str, width: int, height: int, duration: float):
    """CapCut-style caption: bold fill + black stroke + soft drop shadow, no box."""
    import numpy as np
    from moviepy.editor import ImageClip

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    max_box_w = int(width * 0.90)
    wrapped, font = _fit_caption(text, draw, max_box_w)

    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, align="center", spacing=8)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (width - tw) // 2
    y = int(height * 0.78) - th // 2

    fill = _parse_color(getattr(config, "CAPTION_COLOR", "yellow"))
    stroke = _parse_color(getattr(config, "CAPTION_STROKE", "black"))

    # Soft drop shadow layer
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.multiline_text(
        (x + 4, y + 5),
        wrapped,
        font=font,
        fill=(0, 0, 0, 160),
        align="center",
        spacing=8,
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=2))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)

    # Thick outline (stroke) then yellow/white fill
    for ox in range(-3, 4):
        for oy in range(-3, 4):
            if ox == 0 and oy == 0:
                continue
            if abs(ox) + abs(oy) > 5:
                continue
            draw.multiline_text(
                (x + ox, y + oy),
                wrapped,
                font=font,
                fill=stroke,
                align="center",
                spacing=8,
            )
    draw.multiline_text((x, y), wrapped, font=font, fill=fill, align="center", spacing=8)

    arr = np.array(img)
    return ImageClip(arr, ismask=False, transparent=True).set_duration(duration)


def _ffmpeg_bin() -> str:
    import shutil

    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _ffmpeg_upscale(src: Path, dest: Path, out_w: int, out_h: int) -> Path:
    cmd = [
        _ffmpeg_bin(),
        "-y",
        "-i",
        str(src),
        "-vf",
        f"scale={out_w}:{out_h}:flags=lanczos",
        "-c:v",
        "libx264",
        "-preset",
        getattr(config, "EXPORT_PRESET", "slow"),
        "-b:v",
        getattr(config, "EXPORT_BITRATE", "15000k"),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(dest),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return dest
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        log.warning("ffmpeg upscale skipped (%s); keeping assembled file", exc)
        return src


def assemble_video(
    clip_paths: list[Path],
    narration_paths: list[Path],
    *,
    out_path: Path,
    ratio: str = "9:16",
    burn_captions: bool = True,
    caption_lines: list[str] | None = None,
) -> Path:
    from moviepy.editor import (
        AudioFileClip,
        CompositeAudioClip,
        VideoFileClip,
        concatenate_videoclips,
        CompositeVideoClip,
    )
    from moviepy.audio.AudioClip import concatenate_audioclips

    if not clip_paths:
        raise ValueError("No video clips to assemble")

    # Assemble at Flux canvas size; optional 1080p upscale after
    target_w, target_h = config.RATIO_SIZES.get(ratio, config.RATIO_SIZES["9:16"])
    video_clips = []
    for p in clip_paths:
        clip = VideoFileClip(str(p))
        clip = clip.resize(height=target_h) if clip.h >= clip.w else clip.resize(width=target_w)
        clip = clip.crop(
            x_center=clip.w / 2,
            y_center=clip.h / 2,
            width=min(clip.w, target_w),
            height=min(clip.h, target_h),
        )
        video_clips.append(clip)

    video = concatenate_videoclips(video_clips, method="compose")

    existing_audio = [Path(p) for p in narration_paths if Path(p).exists()]
    if existing_audio:
        narr_audio = concatenate_audioclips(
            [AudioFileClip(str(p)).volumex(config.VOICE_VOLUME) for p in existing_audio]
        )
        if narr_audio.duration > video.duration:
            narr_audio = narr_audio.subclip(0, video.duration)
        elif narr_audio.duration < video.duration:
            video = video.subclip(0, max(narr_audio.duration, 1.0))

        audio_layers = [narr_audio]
        bgm_path = _first_bgm()
        if bgm_path:
            bgm = AudioFileClip(str(bgm_path)).volumex(config.BGM_VOLUME)
            if bgm.duration < video.duration:
                bgm = bgm.audio_loop(duration=video.duration)
            else:
                bgm = bgm.subclip(0, video.duration)
            audio_layers.append(bgm)
        video = video.set_audio(CompositeAudioClip(audio_layers))

    if burn_captions and caption_lines:
        try:
            duration_each = video.duration / max(len(caption_lines), 1)
            overlays = []
            for i, line in enumerate(caption_lines):
                if not line.strip():
                    continue
                overlay = _caption_overlay_clip(line, int(video.w), int(video.h), duration_each)
                overlays.append(overlay.set_start(i * duration_each))
            if overlays:
                video = CompositeVideoClip([video, *overlays])
        except Exception as exc:  # noqa: BLE001
            log.warning("Caption burn skipped: %s", exc)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    draft = out_path.with_name(out_path.stem + "_draft.mp4")
    video.write_videofile(
        str(draft),
        fps=config.FPS,
        codec="libx264",
        audio_codec="aac",
        threads=8,
        preset=getattr(config, "EXPORT_PRESET", "slow"),
        bitrate=getattr(config, "EXPORT_BITRATE", "15000k"),
        verbose=False,
        logger=None,
    )

    video.close()
    for c in video_clips:
        c.close()

    if getattr(config, "UPSCALE_ON_EXPORT", False):
        ow, oh = config.OUTPUT_SIZES.get(ratio, (1080, 1920))
        final = _ffmpeg_upscale(draft, out_path, ow, oh)
        if final == out_path and draft.exists() and draft != out_path:
            try:
                draft.unlink()
            except OSError:
                pass
            return out_path
        if final == draft:
            draft.replace(out_path)
            return out_path
        return final

    draft.replace(out_path)
    return out_path
