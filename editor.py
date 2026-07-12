"""Programmatic assembly: concat clips, voice, optional BGM + captions."""
from __future__ import annotations

import logging
from pathlib import Path

# Pillow>=10 removed Image.ANTIALIAS; MoviePy 1.0.3 still references it.
from PIL import Image, ImageDraw, ImageFont

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


def _load_font(size: int = 42) -> ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf",  # Segoe UI Bold — cleaner short-form look
        r"C:\Windows\Fonts\seguisb.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\NirmalaB.ttf",
        r"C:\Windows\Fonts\Nirmala.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\tahoma.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=6)
    return bbox[2] - bbox[0]


def wrap_caption_by_pixels(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.ImageFont,
    max_width_px: int,
    max_lines: int = 4,
) -> str:
    """Word-boundary wrap to a pixel width — never cuts mid-word with [:N]."""
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

    # If a single word is wider than the box, shrink is handled by caller via font size.
    return "\n".join(lines)


def _fit_caption(
    text: str,
    draw: ImageDraw.ImageDraw,
    frame_w: int,
    max_box_w: int,
) -> tuple[str, ImageFont.ImageFont]:
    """Shrink font until full caption wraps cleanly within max lines / width."""
    raw = text.strip()
    for size in (46, 42, 38, 34, 30, 26):
        font = _load_font(size)
        wrapped = wrap_caption_by_pixels(raw, draw, font, max_box_w, max_lines=4)
        # Verify no word was dropped: compare token counts loosely
        if len(wrapped.replace("\n", " ").split()) >= min(len(raw.split()), 1):
            # Prefer versions that keep almost all words
            kept = len(wrapped.replace("\n", " ").split())
            if kept >= len(raw.split()) or size <= 30:
                if kept < len(raw.split()) and size > 26:
                    continue
                return wrapped, font
    font = _load_font(26)
    return wrap_caption_by_pixels(raw, draw, font, max_box_w, max_lines=5), font


def _caption_overlay_clip(text: str, width: int, height: int, duration: float):
    """Pillow-rendered caption — full text, word-safe wrap, stroked for readability."""
    import numpy as np
    from moviepy.editor import ImageClip

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    max_box_w = int(width * 0.88)
    wrapped, font = _fit_caption(text, draw, width, max_box_w)

    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, align="center", spacing=8)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (width - tw) // 2
    y = int(height * 0.76) - th // 2
    pad_x, pad_y = 22, 16

    # Soft plate behind text (less "basic box", still readable on busy frames)
    draw.rounded_rectangle(
        (x - pad_x, y - pad_y, x + tw + pad_x, y + th + pad_y),
        radius=18,
        fill=(0, 0, 0, 140),
    )

    # Stroke then fill for premium short-form readability
    for ox, oy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1)):
        draw.multiline_text(
            (x + ox, y + oy),
            wrapped,
            font=font,
            fill=(0, 0, 0, 220),
            align="center",
            spacing=8,
        )
    draw.multiline_text(
        (x, y),
        wrapped,
        font=font,
        fill=(255, 255, 255, 255),
        align="center",
        spacing=8,
    )

    arr = np.array(img)
    return ImageClip(arr, ismask=False, transparent=True).set_duration(duration)


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
    video.write_videofile(
        str(out_path),
        fps=config.FPS,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="medium",
        verbose=False,
        logger=None,
    )

    video.close()
    for c in video_clips:
        c.close()
    return out_path
