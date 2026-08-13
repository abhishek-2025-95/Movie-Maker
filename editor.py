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


def _lyric_cues_in_window(cues: list[dict], *, t0: float, t1: float) -> list[dict]:
    """Return lyric cues that overlap [t0, t1)."""
    out = []
    for c in cues or []:
        start = float(c.get("start") or 0.0)
        end = float(c.get("end") or start)
        if end > t0 and start < t1:
            out.append(c)
    return out


def cleanup_caption_text(text: str) -> str:
    """Fix glued words / punctuation so captions stay readable (Don'tgo → Don't go)."""
    import re

    if not text:
        return ""
    s = text.replace("\u00a0", " ").strip()
    s = s.replace("  ", " ")
    s = re.sub(r"\s+", " ", s)
    fixes = (
        (r"\bDon'tgo\b", "Don't go"),
        (r"\bDontgo\b", "Don't go"),
        (r"\bDon't\.Breathe\b", "Don't. Breathe"),
        (r"\binthere\b", "in there"),
        (r"\bLook\.LOOK\b", "LOOK"),
        (r"\bNobodyinside\b", "Nobody inside"),
        (r"([a-z])([A-Z])", r"\1 \2"),
        (r"([.!?,:;])([A-Za-z])", r"\1 \2"),
        (r"(n'\w)([a-z]{2,})", r"\1 \2"),
    )
    for pat, rep in fixes:
        s = re.sub(pat, rep, s)
    return s.strip()


def _wrap_caption_fit(text: str, *, wrap_w: int, max_lines: int) -> str:
    """Wrap caption so every word stays on-screen — never truncate mid-sentence."""
    import textwrap

    cleaned = cleanup_caption_text(text)
    if not cleaned:
        return ""
    words = cleaned.split()
    # Prefer complete sentence; if too long for max_lines, tighten wrap then shrink word count
    for width in (wrap_w, max(14, wrap_w - 4), max(12, wrap_w - 8)):
        wrapped = textwrap.fill(" ".join(words), width=width)
        lines = wrapped.splitlines()
        if len(lines) <= max_lines:
            return wrapped
    # Last resort: keep earliest words that fit max_lines at wrap_w (whole words only)
    kept: list[str] = []
    for w in words:
        trial = textwrap.fill(" ".join(kept + [w]), width=wrap_w)
        if len(trial.splitlines()) > max_lines:
            break
        kept.append(w)
    out = textwrap.fill(" ".join(kept), width=wrap_w) if kept else textwrap.fill(words[0], width=wrap_w)
    # Ensure we don't end on a dangling conjunction
    dangling = {"the", "a", "an", "of", "to", "for", "and", "or", "in", "on", "as", "only"}
    lines = out.splitlines()
    if lines:
        last_words = lines[-1].split()
        while last_words and last_words[-1].lower().strip(".,;:") in dangling:
            last_words.pop()
        if last_words:
            lines[-1] = " ".join(last_words)
        out = "\n".join(lines)
    return out


def wrap_caption_words(text: str, max_words: int = 6) -> str:
    """Premium caption wrap: max N words per line (default 5–6)."""
    words = cleanup_caption_text(text).split()
    if not words:
        return ""
    max_words = max(3, int(max_words or 6))
    lines = []
    for i in range(0, len(words), max_words):
        lines.append(" ".join(words[i : i + max_words]))
    return "\n".join(lines)


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
        # Premium Latin first for EN cinematic captions
        str(config.ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf"),
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\impact.ttf",
        # Hindi/Devanagari
        str(config.ROOT / "assets" / "fonts" / "NotoSansDevanagari-Bold.ttf"),
        r"C:\Windows\Fonts\NirmalaB.ttf",
        r"C:\Windows\Fonts\Nirmala.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
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


def _caption_overlay_clip(
    text: str,
    width: int,
    height: int,
    duration: float,
    *,
    fade_out: float = 0.0,
    position: str | None = None,
    y_rel: float | None = None,
):
    """Reliable MoviePy TextClip captions (ImageMagick) — PyCaps permanently removed."""
    import os

    from moviepy.config import change_settings
    from moviepy.editor import ColorClip, TextClip

    # Windows: MoviePy needs an explicit ImageMagick binary
    magick = os.environ.get("IMAGEMAGICK_BINARY")
    if not magick:
        candidates = [
            Path(r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"),
            Path(r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"),
            Path(r"C:\Program Files\ImageMagick-7.1.0-Q16-HDRI\magick.exe"),
        ]
        for c in candidates:
            if c.exists():
                magick = str(c)
                break
        if not magick:
            import shutil

            magick = shutil.which("magick")
    if magick:
        change_settings({"IMAGEMAGICK_BINARY": magick})

    cleaned = cleanup_caption_text(text)
    wrap_w = int(getattr(config, "CAPTION_TEXTWRAP_WIDTH", 25))
    max_lines = int(getattr(config, "CAPTION_MAX_LINES", 3))
    wrapped = _wrap_caption_fit(cleaned, wrap_w=wrap_w, max_lines=max_lines) if cleaned else ""
    if not wrapped:
        return ColorClip(size=(width, height), color=(0, 0, 0)).set_opacity(0).set_duration(duration)

    font_path = config.ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf"
    font = str(font_path) if font_path.exists() else str(
        getattr(config, "CAPTION_FONT", "Montserrat-Bold")
    )
    box_w = int(getattr(config, "CAPTION_BOX_W", 960))
    fontsize = int(getattr(config, "CAPTION_FONTSIZE", 48))
    stroke_w = int(getattr(config, "CAPTION_STROKE_WIDTH", 2))
    bottom_margin = int(getattr(config, "CAPTION_BOTTOM_MARGIN", 72))

    # Absolute hard-stop: never longer than the hosting video/audio window
    duration = max(0.05, float(duration))

    txt = TextClip(
        wrapped,
        font=font,
        fontsize=fontsize,
        color=str(getattr(config, "CAPTION_COLOR", "white")),
        stroke_color=str(getattr(config, "CAPTION_STROKE", "black")),
        stroke_width=stroke_w,
        method="caption",
        size=(box_w, None),
        align="center",
    )
    txt = txt.set_duration(duration)
    if fade_out and fade_out > 0 and duration > fade_out + 0.05:
        txt = txt.crossfadeout(float(fade_out))

    pos = (position or "bottom").lower()
    if pos == "top":
        rel = float(y_rel if y_rel is not None else getattr(config, "RAW_CAPTION_Y_REL", 0.15))
        y = max(0, int(float(height) * rel))
        return txt.set_position(("center", y))
    if pos == "center":
        rel = float(y_rel if y_rel is not None else 0.42)
        y = max(0, int(float(height) * rel - float(txt.h) / 2))
        return txt.set_position(("center", y))
    # Absolute bottom lock — entire block on-screen (relative 0.82 was clipping last lines)
    y = max(0, int(height) - int(txt.h) - bottom_margin)
    return txt.set_position(("center", y))


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
    # P1: Real-ESRGAN when weights + spandrel available
    if getattr(config, "EXPORT_USE_REALESRGAN", False):
        try:
            from quality_os.upscale import realesrgan_available, upscale_video_to_master

            if realesrgan_available():
                return upscale_video_to_master(src, dest, out_w=out_w, out_h=out_h)
        except Exception as exc:  # noqa: BLE001
            log.warning("Real-ESRGAN upscale failed (%s); HQ ffmpeg fallback", exc)

    vf = f"scale={out_w}:{out_h}:flags=lanczos"
    if getattr(config, "EXPORT_UPSCALE_HQ_CHAIN", False):
        vf = (
            f"{vf},"
            f"eq=contrast=1.08:brightness=-0.02:saturation=0.92:gamma=0.95,"
            f"unsharp=3:3:0.55:3:3:0.0,"
            f"noise=alls=6:allf=t"
        )
    elif getattr(config, "EXPORT_UPSCALE_UNSHARP", False):
        # Mild sharpen after soft Wan→1080 upscale (open-source, no extra models).
        vf = f"{vf},unsharp=5:5:0.6:5:5:0.0"
    cmd = [
        _ffmpeg_bin(),
        "-y",
        "-i",
        str(src),
        "-vf",
        vf,
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


def _ffprobe_duration(path: Path) -> float:
    cmd = [
        _ffmpeg_bin().replace("ffmpeg", "ffprobe") if False else "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nk=1:nw=1",
        str(path),
    ]
    # Prefer ffprobe next to ffmpeg / on PATH
    import shutil

    ffprobe = shutil.which("ffprobe") or "ffprobe"
    cmd[0] = ffprobe
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
        return float(out)
    except Exception:
        return 0.0


def _ffmpeg_fit_duration(src: Path, dest: Path, target: float, *, fps: int | None = None) -> Path:
    """Trim or freeze-pad via ffmpeg (avoids MoviePy get_frame seek bugs on Wan H264)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = max(0.1, float(target))
    dur = _ffprobe_duration(src)
    fps = int(fps or getattr(config, "FPS", 24) or 24)
    if dur <= 0:
        # Remux only
        cmd = [
            _ffmpeg_bin(),
            "-y",
            "-i",
            str(src),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(dest),
        ]
    elif dur >= target - 0.04:
        cmd = [
            _ffmpeg_bin(),
            "-y",
            "-i",
            str(src),
            "-t",
            f"{target:.4f}",
            "-vf",
            f"fps={fps},format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-an",
            str(dest),
        ]
    elif not getattr(config, "QUALITY_ALLOW_FREEZE_PAD", True):
        log.warning(
            "freeze-pad suppressed (QUALITY_FIRST); leaving duration %.2fs < target %.2fs",
            dur,
            target,
        )
        cmd = [
            _ffmpeg_bin(),
            "-y",
            "-i",
            str(src),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(dest),
        ]
    else:
        pad = max(0.0, target - dur)
        # Clone last frame for the shortfall
        cmd = [
            _ffmpeg_bin(),
            "-y",
            "-i",
            str(src),
            "-vf",
            f"fps={fps},tpad=stop_mode=clone:stop_duration={pad:.4f},format=yuv420p",
            "-t",
            f"{target:.4f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-an",
            str(dest),
        ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        if dest.exists() and dest.stat().st_size > 1000:
            return dest
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        log.warning("ffmpeg fit_duration failed (%s); falling back to MoviePy", exc)
    return src


def _fit_clip_to_duration(clip, target: float):
    """Trim or freeze-pad in MoviePy only — no full-file ffmpeg remux (preserves edges)."""
    from moviepy.editor import ImageClip, concatenate_videoclips

    if target <= 0:
        return clip
    if clip.duration >= target - 0.05:
        return clip.subclip(0, min(target, max(0.05, float(clip.duration) - 0.001)))

    if not getattr(config, "QUALITY_ALLOW_FREEZE_PAD", True):
        log.warning(
            "freeze-pad suppressed (QUALITY_FIRST); leaving duration %.2fs < target %.2fs",
            clip.duration,
            target,
        )
        return clip

    pad = float(target) - float(clip.duration)
    frame = None
    # Prefer a safe mid/late frame; avoid exact EOF seek bugs on Wan H264
    for frac in (0.92, 0.85, 0.5, 0.1):
        try:
            t = max(0.0, min(float(clip.duration) * frac, float(clip.duration) - 0.05))
            frame = clip.get_frame(t)
            break
        except Exception:
            continue
    if frame is None:
        # Last resort: one-frame ffmpeg extract (not a full remux)
        try:
            import tempfile

            src = getattr(clip, "filename", None)
            if src:
                tmp = Path(tempfile.mkstemp(suffix=".png")[1])
                cmd = [
                    _ffmpeg_bin(),
                    "-y",
                    "-sseof",
                    "-0.12",
                    "-i",
                    str(src),
                    "-frames:v",
                    "1",
                    str(tmp),
                ]
                subprocess.run(cmd, check=True, capture_output=True)
                if tmp.exists() and tmp.stat().st_size > 100:
                    from PIL import Image
                    import numpy as np

                    frame = np.asarray(Image.open(tmp).convert("RGB"))
                try:
                    tmp.unlink()
                except OSError:
                    pass
        except Exception as exc:  # noqa: BLE001
            log.warning("Freeze-pad frame extract failed (%s); keeping short clip", exc)
            return clip
    if frame is None:
        return clip
    freeze = ImageClip(frame).set_duration(pad)
    freeze = freeze.set_fps(getattr(clip, "fps", None) or config.FPS)
    return concatenate_videoclips([clip, freeze], method="compose")


def _apply_smash_audio(clip, boost_seconds: float = 0.5, gain: float = 1.55):
    """Hard visual cut + brief audio punch for smash_cut."""
    from moviepy.audio.AudioClip import concatenate_audioclips

    if clip.audio is None:
        return clip
    a = clip.audio
    if a.duration <= boost_seconds:
        return clip.set_audio(a.volumex(gain))
    punch = a.subclip(0, boost_seconds).volumex(gain)
    rest = a.subclip(boost_seconds)
    return clip.set_audio(concatenate_audioclips([punch, rest]))


def _stitch_with_transitions(clips: list, transitions: list[str]):
    """Concatenate clips using LLM transition keys (default hard_cut)."""
    from moviepy.editor import CompositeVideoClip, concatenate_videoclips
    from director import normalize_transition

    if not clips:
        raise ValueError("No clips")
    if len(clips) == 1:
        return clips[0]

    td = float(getattr(config, "TRANSITION_DURATION", 0.85))
    prepared = list(clips)
    needs_overlap = False

    for i in range(len(prepared) - 1):
        prev_t = normalize_transition(
            transitions[i] if i < len(transitions) else "hard_cut"
        )
        fade = min(td, prepared[i].duration * 0.35, prepared[i + 1].duration * 0.35)
        if prev_t == "crossfade" and fade > 0.05:
            prepared[i] = prepared[i].fadeout(fade)
            prepared[i + 1] = prepared[i + 1].crossfadein(fade)
            needs_overlap = True
        elif prev_t == "fade_to_black" and fade > 0.05:
            prepared[i] = prepared[i].fadeout(fade)
            prepared[i + 1] = prepared[i + 1].fadein(fade)
        elif prev_t == "smash_cut":
            prepared[i + 1] = _apply_smash_audio(prepared[i + 1])

    if not needs_overlap:
        return concatenate_videoclips(prepared, method="compose")

    # Overlapping crossfades need a composite timeline
    layers = []
    t = 0.0
    for i, clip in enumerate(prepared):
        if i > 0:
            prev_t = normalize_transition(
                transitions[i - 1] if i - 1 < len(transitions) else "hard_cut"
            )
            if prev_t == "crossfade":
                fade = min(td, clips[i - 1].duration * 0.35, clips[i].duration * 0.35)
                if fade > 0.05:
                    t = max(0.0, t - fade)
        layers.append(clip.set_start(t))
        t += clip.duration
    total = max(layer.start + layer.duration for layer in layers)
    return CompositeVideoClip(layers, size=prepared[0].size).set_duration(total)

def assemble_video(
    clip_paths: list[Path],
    narration_paths: list[Path],
    *,
    out_path: Path,
    ratio: str = "9:16",
    burn_captions: bool = True,
    caption_lines: list[str] | None = None,
    transitions: list[str] | None = None,
    screenplay_meta: dict | None = None,
) -> Path:
    from moviepy.editor import (
        AudioFileClip,
        CompositeAudioClip,
        VideoFileClip,
        CompositeVideoClip,
    )

    if not clip_paths:
        raise ValueError("No video clips to assemble")

    meta = dict(screenplay_meta or {})
    # Assemble at Flux canvas size; optional 1080p upscale after
    target_w, target_h = config.RATIO_SIZES.get(ratio, config.RATIO_SIZES["9:16"])
    n = len(clip_paths)
    transitions = list(transitions or ["hard_cut"] * n)
    while len(transitions) < n:
        transitions.append("hard_cut")
    transitions[-1] = "none"

    if n >= 2:
        # Guard: refuse silent single-shot failure modes (identical paths)
        uniq = {str(Path(p).resolve()) for p in clip_paths}
        if len(uniq) < n:
            log.error(
                "Assembly abort: duplicate clip paths (%s unique / %s scenes) — "
                "Scene stills were not generated separately",
                len(uniq),
                n,
            )
            raise ValueError("Duplicate scene clips — master-still lock or stitch bug")

    paired = []
    for i, p in enumerate(clip_paths):
        src = Path(p)
        narr_p = Path(narration_paths[i]) if i < len(narration_paths) else None
        reel_profiles = {
            "analog_phone_12s",
            "echo_chamber_12s",
            "raw_reel_12s",
            "wingsuit_15s",
            "wingsuit_oneshot_15s",
            "usa_sports_quiz_12s",
            "music_video_lyric_180s",
            "romance_love_120s",
        }
        is_timed_reel = meta.get("reel_profile") in reel_profiles
        beat_durs = meta.get("beat_durations") or []
        min_scene = float(getattr(config, "SECONDS_PER_SCENE", 5) or 5)
        target_beat = float(beat_durs[i]) if i < len(beat_durs) else min_scene

        # Panel specs may be 16:9; delivery canvas is still job ratio (usually 9:16)
        panel_specs = meta.get("panel_specs") or []
        panel_ratio = None
        if i < len(panel_specs) and isinstance(panel_specs[i], dict):
            panel_ratio = panel_specs[i].get("ratio")
        fit_w, fit_h = target_w, target_h
        if panel_ratio and panel_ratio in config.RATIO_SIZES:
            fit_w, fit_h = config.RATIO_SIZES[panel_ratio]

        still_ext = {".png", ".jpg", ".jpeg", ".webp"}
        if src.suffix.lower() in still_ext:
            from utils import ken_burns_clip

            plan = (meta.get("beat_plan") or [])
            zoom = 1.06
            if i < len(plan) and isinstance(plan[i], dict):
                zoom = float(plan[i].get("zoom_end") or zoom)
            clip = ken_burns_clip(
                src,
                duration=target_beat if is_timed_reel else min_scene,
                out_w=fit_w,
                out_h=fit_h,
                zoom_end=zoom,
            )
            log.info(
                "Scene %s Ken Burns still: dur=%.2fs file=%s",
                i + 1,
                clip.duration,
                src.name,
            )
        else:
            clip = VideoFileClip(str(src))
            clip = clip.resize(height=fit_h) if clip.h >= clip.w else clip.resize(width=fit_w)
            clip = clip.crop(
                x_center=clip.w / 2,
                y_center=clip.h / 2,
                width=min(clip.w, fit_w),
                height=min(clip.h, fit_h),
            )

        if is_timed_reel and src.suffix.lower() not in still_ext:
            clip = _fit_clip_to_duration(clip, target_beat)
            if float(clip.duration) > target_beat + 0.05:
                clip = clip.subclip(0, target_beat)
            log.info(
                "Scene %s timed-reel MoviePy-fit: video=%.2fs target=%.2fs file=%s",
                i + 1,
                clip.duration,
                target_beat,
                src.name,
            )

        # Attach VO: cinematic path, or timed romance that still needs narration
        want_vo = (
            ((not is_timed_reel) or bool(meta.get("mux_vo")) or meta.get("reel_profile") == "romance_love_120s")
            and narr_p
            and narr_p.exists()
        )
        if want_vo:
            narr = AudioFileClip(str(narr_p)).volumex(config.VOICE_VOLUME)
            if not is_timed_reel:
                # Keep cinematic hold: never crush Wan ~5s clips down to tiny VO lines
                target_dur = max(float(clip.duration), float(narr.duration), min_scene)
                clip = _fit_clip_to_duration(clip, target_dur)
            if narr.duration < clip.duration:
                from moviepy.audio.AudioClip import AudioClip, concatenate_audioclips

                gap = clip.duration - narr.duration
                silence = AudioClip(lambda t: 0, duration=gap, fps=44100)
                narr = concatenate_audioclips([narr, silence])
            elif narr.duration > clip.duration:
                narr = narr.subclip(0, clip.duration)
            clip = clip.set_audio(narr)
            log.info(
                "Scene %s sync: video=%.2fs vo=%.2fs file=%s",
                i + 1,
                clip.duration,
                narr.duration,
                Path(p).name,
            )
        elif not is_timed_reel:
            log.warning("Scene %s missing narration; keeping raw clip duration", i + 1)
        paired.append(clip)

    # True programmatic split / delivery timeline (compose_plan)
    compose_plan = meta.get("compose_plan") or []
    delivery = paired
    delivery_transitions = transitions
    if compose_plan:
        from utils import compose_vertical_split

        built = []
        built_trans: list[str] = []
        for step in compose_plan:
            stype = str(step.get("type") or "single").lower()
            sources = list(step.get("sources") or [])
            dur = float(step.get("duration") or 0) or None
            tr = str(step.get("transition_to_next") or "hard_cut")
            if stype == "vsplit" and len(sources) >= 2:
                a_i, b_i = int(sources[0]), int(sources[1])
                if a_i < len(paired) and b_i < len(paired):
                    stacked = compose_vertical_split(
                        paired[a_i],
                        paired[b_i],
                        out_w=target_w,
                        out_h=target_h,
                        duration=dur,
                    )
                    built.append(stacked)
                    built_trans.append(tr)
                    log.info(
                        "Compose vsplit panels %s+%s → %.2fs %sx%s",
                        a_i,
                        b_i,
                        stacked.duration,
                        target_w,
                        target_h,
                    )
            elif sources:
                si = int(sources[0])
                if si < len(paired):
                    c = paired[si]
                    if dur and float(c.duration) < dur - 0.05:
                        c = _fit_clip_to_duration(c, dur)
                    elif dur and float(c.duration) > dur + 0.05:
                        c = c.subclip(0, dur)
                    # Reunion / full plate must fill 9:16 canvas
                    if c.w != target_w or c.h != target_h:
                        c = c.resize(height=target_h) if c.h * target_w >= c.w * target_h else c.resize(width=target_w)
                        c = c.crop(
                            x_center=c.w / 2,
                            y_center=c.h / 2,
                            width=min(c.w, target_w),
                            height=min(c.h, target_h),
                        )
                    built.append(c)
                    built_trans.append(tr)
        if built:
            delivery = built
            delivery_transitions = built_trans
            delivery_transitions[-1] = "none"
            log.info("Compose plan active: %s delivery beats", len(delivery))

    # Burn captions onto EACH delivery beat BEFORE stitch
    # (lyric_cues mode burns on the full timeline after stitch)
    if burn_captions and caption_lines and meta.get("caption_mode") != "lyric_cues":
        try:
            fade = float(getattr(config, "CAPTION_FADEOUT_SEC", 0.5))
            cap_pos = str(meta.get("caption_position") or "").lower()
            if not cap_pos and (
                meta.get("director_mode") == "raw"
                or meta.get("reel_profile")
                in {
                    "analog_phone_12s",
                    "echo_chamber_12s",
                    "raw_reel_12s",
                    "wingsuit_15s",
                    "wingsuit_oneshot_15s",
                    "usa_sports_quiz_12s",
                    "music_video_lyric_180s",
                }
            ):
                cap_pos = str(
                    meta.get("caption_position")
                    or getattr(config, "RAW_CAPTION_POSITION", "top")
                    or "top"
                )
            burned = []
            for i, clip in enumerate(delivery):
                line = caption_lines[i] if i < len(caption_lines) else ""
                # Locked Reel/raw overlay wins over any hallucinated line
                # (quiz uses per-beat narration — never flatten to one overlay)
                if meta.get("text_overlay") and meta.get("caption_mode") != "per_beat":
                    line = str(meta.get("text_overlay"))
                cleaned = cleanup_caption_text(line)
                if not cleaned:
                    burned.append(clip)
                    continue
                audio_dur = float(clip.audio.duration) if clip.audio is not None else float(clip.duration)
                # Hard-stop: never longer than video or audio window
                cap_dur = min(float(clip.duration), audio_dur)
                is_last = i == len(delivery) - 1
                overlay = _caption_overlay_clip(
                    cleaned,
                    int(clip.w),
                    int(clip.h),
                    cap_dur,
                    fade_out=fade if is_last else 0.0,
                    position=cap_pos or "bottom",
                    y_rel=(
                        float(getattr(config, "RAW_CAPTION_Y_REL", 0.15))
                        if (cap_pos or "") == "top"
                        else (0.42 if (cap_pos or "") == "center" else None)
                    ),
                )
                composed = CompositeVideoClip([clip, overlay.set_start(0)]).set_duration(clip.duration)
                if clip.audio is not None:
                    composed = composed.set_audio(clip.audio)
                burned.append(composed)
                log.info(
                    "Caption scene %s dur=%.2fs fade_out=%s pos=%s",
                    i + 1,
                    cap_dur,
                    fade if is_last else 0.0,
                    cap_pos or "bottom",
                )
            delivery = burned
        except Exception as exc:  # noqa: BLE001
            log.warning("Caption burn skipped: %s", exc)

    video = _stitch_with_transitions(delivery, delivery_transitions)
    log.info(
        "Stitched %s delivery beats (transitions=%s) → %.2fs",
        len(delivery),
        delivery_transitions,
        video.duration,
    )

    # Timed reels: custom audio beds (horror / lo-fi) + loop mute
    # Music video uses master song audio instead of synthetic beds.
    reel_profile = meta.get("reel_profile")
    if reel_profile == "music_video_lyric_180s":
        try:
            target_total = float(meta.get("loop_end_sec", meta.get("target_duration_sec", 180.0)))
            if video.duration > target_total + 0.05:
                video = video.subclip(0, target_total)
            elif video.duration < target_total - 0.05:
                # Pad last frame hold if short
                from moviepy.editor import concatenate_videoclips

                gap = target_total - float(video.duration)
                hold = video.to_ImageClip(t=max(0, float(video.duration) - 0.04)).set_duration(gap)
                video = concatenate_videoclips([video, hold], method="compose")
            master = Path(str(meta.get("master_audio") or ""))
            if master.exists():
                song = AudioFileClip(str(master))
                song = song.subclip(0, min(float(song.duration), float(video.duration)))
                video = video.set_audio(song)
                log.info(
                    "Music video master audio muxed: %s (%.2fs)",
                    master.name,
                    float(song.duration),
                )
            else:
                log.warning("Music video master_audio missing: %s", master)
        except Exception as exc:  # noqa: BLE001
            log.warning("Music video audio/pad skipped: %s", exc)

        if burn_captions and meta.get("caption_mode") == "lyric_cues":
            try:
                from utils import load_lyric_cues

                align = Path(str(meta.get("lyric_alignment") or ""))
                cues = load_lyric_cues(align) if align.exists() else []
                overlays = []
                for c in cues:
                    cleaned = cleanup_caption_text(str(c.get("text") or ""))
                    if not cleaned:
                        continue
                    start = float(c["start"])
                    end = min(float(c["end"]), float(video.duration))
                    if end <= start or start >= float(video.duration):
                        continue
                    dur = end - start
                    ov = _caption_overlay_clip(
                        cleaned,
                        int(video.w),
                        int(video.h),
                        dur,
                        fade_out=0.0,
                        position=str(meta.get("caption_position") or "bottom"),
                    )
                    overlays.append(ov.set_start(start))
                if overlays:
                    video = CompositeVideoClip(
                        [video, *overlays], size=(int(video.w), int(video.h))
                    ).set_duration(video.duration).set_audio(video.audio)
                    log.info("Burned %s lyric cues on music video timeline", len(overlays))
            except Exception as exc:  # noqa: BLE001
                log.warning("Lyric cue burn skipped: %s", exc)

    elif reel_profile in {
        "analog_phone_12s",
        "echo_chamber_12s",
        "raw_reel_12s",
        "wingsuit_15s",
        "wingsuit_oneshot_15s",
        "usa_sports_quiz_12s",
    }:
        try:
            target_total = float(meta.get("loop_end_sec", meta.get("target_duration_sec", 11.9)))
            silence_tail = float(
                meta.get(
                    "loop_end_silence",
                    getattr(config, "REEL_LOOP_END_SILENCE", 0.5),
                )
            )
            if video.duration > target_total + 0.05:
                video = video.subclip(0, target_total)
            bed_path = out_path.parent / f"{out_path.stem}_reel_bed.wav"
            audio_profile = str(meta.get("audio_profile") or "")
            if reel_profile == "analog_phone_12s" or audio_profile == "horror":
                from utils import build_analog_horror_bed

                glitch_at = float(meta.get("glitch_at_sec", 6.0))
                build_analog_horror_bed(
                    float(video.duration),
                    glitch_at=min(glitch_at, max(0.5, float(video.duration) - 0.5)),
                    out_path=bed_path,
                    loop_end_silence=silence_tail,
                )
                hit_at = glitch_at
            elif reel_profile in {"wingsuit_15s", "wingsuit_oneshot_15s"} or audio_profile == "wind_rush":
                from utils import build_wind_rush_bed

                whoosh_at = float(meta.get("whoosh_at_sec", 5.0))
                build_wind_rush_bed(
                    float(video.duration),
                    out_path=bed_path,
                    whoosh_at=min(whoosh_at, max(0.5, float(video.duration) - 0.5)),
                    loop_end_silence=min(silence_tail, 0.35),
                )
                hit_at = whoosh_at
            else:
                from utils import build_lofi_echo_bed

                collapse_at = float(meta.get("collapse_at_sec", 8.0))
                build_lofi_echo_bed(
                    float(video.duration),
                    collapse_at=min(collapse_at, max(0.5, float(video.duration) - 0.5)),
                    out_path=bed_path,
                    loop_end_silence=silence_tail,
                )
                hit_at = collapse_at
            bed = AudioFileClip(str(bed_path))
            if bed.duration > video.duration:
                bed = bed.subclip(0, video.duration)
            try:
                if silence_tail > 0 and bed.duration > silence_tail + 0.05:
                    bed = bed.audio_fadeout(silence_tail)
            except Exception:  # noqa: BLE001
                pass
            video = video.set_audio(bed)
            log.info(
                "Reel audio bed mixed (profile=%s hit@%.1fs, duration=%.2fs, mute_tail=%.2fs)",
                reel_profile,
                hit_at,
                video.duration,
                silence_tail,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Reel audio bed skipped: %s", exc)

    # Pacing: trim dead air; optional deliberate 1s black hold WITHOUT text
    timed_reels = {
        "analog_phone_12s",
        "echo_chamber_12s",
        "raw_reel_12s",
        "wingsuit_15s",
        "wingsuit_oneshot_15s",
        "usa_sports_quiz_12s",
        "music_video_lyric_180s",
        "romance_love_120s",
    }
    # Romance is duration-timed but still wants cinematic BGM under VO (no dead-air crush)
    allow_cinematic_bgm = (
        meta.get("reel_profile") not in timed_reels
        or meta.get("reel_profile") == "romance_love_120s"
    )
    if meta.get("reel_profile") not in timed_reels and video.audio is not None:
        audio_end = float(video.audio.duration)
        if video.duration > audio_end + 0.08:
            video = video.subclip(0, audio_end)
            log.info("Trimmed trailing dead air to audio end=%.2fs", audio_end)
        hold = float(getattr(config, "END_BLACK_HOLD_SEC", 1.0) or 0.0)
        if hold > 0:
            from moviepy.audio.AudioClip import AudioClip
            from moviepy.editor import ColorClip, concatenate_videoclips

            black = ColorClip(size=(int(video.w), int(video.h)), color=(0, 0, 0), duration=hold)
            silence = AudioClip(lambda t: 0, duration=hold, fps=44100)
            black = black.set_audio(silence)
            video = concatenate_videoclips([video, black], method="compose")
            log.info("Appended %.1fs black hold without text", hold)

    bgm_path = _first_bgm()
    if allow_cinematic_bgm and bgm_path and video.audio is not None:
        bgm = AudioFileClip(str(bgm_path)).volumex(config.BGM_VOLUME)
        if bgm.duration < video.duration:
            bgm = bgm.audio_loop(duration=video.duration)
        else:
            bgm = bgm.subclip(0, video.duration)
        # Keep end black silent of VO but allow quiet BGM duck already applied
        video = video.set_audio(CompositeAudioClip([video.audio, bgm]))
    elif allow_cinematic_bgm and bgm_path and video.audio is None:
        bgm = AudioFileClip(str(bgm_path)).volumex(config.BGM_VOLUME)
        bgm = bgm.subclip(0, min(bgm.duration, video.duration))
        video = video.set_audio(bgm)

    # Final cinematic layer: 35mm grain + vignette + shadow grade
    try:
        from utils import apply_cinematic_layering

        video = apply_cinematic_layering(
            video, grade=str(meta.get("cinematic_grade") or "") or None
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Cinematic layering skipped: %s", exc)

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
    for c in paired:
        try:
            c.close()
        except Exception:
            pass

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
