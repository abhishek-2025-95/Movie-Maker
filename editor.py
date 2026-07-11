"""Programmatic assembly: concat clips, voice, optional BGM + captions."""
from __future__ import annotations

import logging
import textwrap
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
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\seguiemj.ttf",
        r"C:\Windows\Fonts\Nirmala.ttf",  # good Hindi coverage on Windows
        r"C:\Windows\Fonts\tahoma.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _caption_overlay_clip(text: str, width: int, height: int, duration: float):
    """Pillow-rendered caption — no ImageMagick required."""
    import numpy as np
    from moviepy.editor import ImageClip

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _load_font(42 if width >= 700 else 32)
    wrapped = textwrap.fill(text.strip()[:140], width=28 if width < 900 else 40)
    # Measure text block
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, align="center", spacing=6)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (width - tw) // 2
    y = int(height * 0.78) - th // 2
    pad = 18
    draw.rounded_rectangle(
        (x - pad, y - pad, x + tw + pad, y + th + pad),
        radius=16,
        fill=(0, 0, 0, 150),
    )
    draw.multiline_text((x, y), wrapped, font=font, fill=(255, 255, 255, 255), align="center", spacing=6)
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
