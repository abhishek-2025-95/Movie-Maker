"""Build Mixkit B-roll lyric music video + premium PyCaps karaoke.

No Flux/Wan. Downloads free Mixkit stock, stitches to 180s @ 1920x1080,
muxes FINAL_HIT_SONG.wav, burns cinematic_premium.css via PyCaps.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "final_outputs"
TEMP = ROOT / "temp" / "broll_lyric_mv"
BROLL_DIR = TEMP / "clips"
CSS = ROOT / "assets" / "captions" / "music_lyric_premium.css"
SONG = Path(r"C:\Users\user\Documents\SunoX\workspace\FINAL_HIT_SONG.wav")
ALIGN = Path(r"C:\Users\user\Documents\SunoX\workspace\lyric_alignment.json")
TARGET_SEC = 180.0
W, H = 1920, 1080
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

log = logging.getLogger("broll_lyric_mv")

# Asset library (Mixkit free). Labels are unique filenames under BROLL_DIR.
ASSETS = {
    "intro_window": "https://assets.mixkit.co/videos/28085/28085-720.mp4",
    "coffee_night": "https://assets.mixkit.co/videos/41859/41859-1080.mp4",  # was kitchen brunch
    "apartment": "https://assets.mixkit.co/videos/4029/4029-1080.mp4",
    "bedroom": "https://assets.mixkit.co/videos/3111/3111-1080.mp4",
    "skyline_a": "https://assets.mixkit.co/videos/49845/49845-1080.mp4",
    "skyline_b": "https://assets.mixkit.co/videos/49846/49846-1080.mp4",
    "skyline_c": "https://assets.mixkit.co/videos/1606/1606-1080.mp4",
    "rain_city": "https://assets.mixkit.co/videos/23662/23662-720.mp4",
    "rain_puddle": "https://assets.mixkit.co/videos/18312/18312-1080.mp4",
    "rain_soft": "https://assets.mixkit.co/videos/25375/25375-720.mp4",
    "neon_street": "https://assets.mixkit.co/videos/4451/4451-1080.mp4",  # quiet Tokyo night street
    "neon_street_b": "https://assets.mixkit.co/videos/41160/41160-1080.mp4",  # big-city night streets
    "wet_street": "https://assets.mixkit.co/videos/4332/4332-1080.mp4",  # Times Square rainy night
    "fire_escape": "https://assets.mixkit.co/videos/41158/41158-1080.mp4",  # city street night cars
    "lonely": "https://assets.mixkit.co/videos/35426/35426-720.mp4",
    "subway": "https://assets.mixkit.co/videos/1622/1622-1080.mp4",
    "street": "https://assets.mixkit.co/videos/4231/4231-1080.mp4",
    "window_city": "https://assets.mixkit.co/videos/20311/20311-720.mp4",  # rain on car window / city lights
    "window_city_b": "https://assets.mixkit.co/videos/49878/49878-1080.mp4",  # quiet aerial city night
}

# Timeline: longer verse holds; chorus denser ~2.5–3s skyline/rain/neon street.
# Each entry: (asset_key, start_sec, end_sec, ken_burns_zoom)
PLATES: list[tuple[str, float, float, float]] = [
    # Verse / intro holds
    ("intro_window", 0.0, 9.0, 1.08),
    ("coffee_night", 9.0, 18.0, 1.06),
    ("apartment", 18.0, 32.0, 1.05),
    ("bedroom", 32.0, 50.0, 1.06),
    # Chorus A — dense
    ("skyline_a", 50.0, 53.0, 1.04),
    ("rain_city", 53.0, 56.0, 1.05),
    ("neon_street", 56.0, 59.0, 1.04),
    ("skyline_b", 59.0, 62.0, 1.05),
    ("rain_puddle", 62.0, 65.0, 1.04),
    ("wet_street", 65.0, 68.0, 1.05),
    ("skyline_c", 68.0, 71.0, 1.04),
    ("rain_city", 71.0, 74.0, 1.05),
    ("neon_street_b", 74.0, 77.0, 1.04),
    ("skyline_a", 77.0, 80.0, 1.05),
    ("rain_soft", 80.0, 85.0, 1.04),
    # Verse 2 holds
    ("lonely", 85.0, 99.0, 1.07),
    ("subway", 99.0, 118.0, 1.04),
    ("street", 118.0, 125.0, 1.05),
    # Chorus B — dense (rainy sidewalk / fire escape, no cyber neon)
    ("rain_puddle", 125.0, 128.0, 1.04),
    ("fire_escape", 128.0, 131.0, 1.05),
    ("skyline_b", 131.0, 134.0, 1.04),
    ("wet_street", 134.0, 137.0, 1.05),
    ("rain_city", 137.0, 140.0, 1.04),
    ("neon_street", 140.0, 143.0, 1.05),
    ("fire_escape", 143.0, 146.0, 1.04),
    ("skyline_c", 146.0, 149.0, 1.05),
    # Bridge
    ("rain_puddle", 149.0, 164.0, 1.06),
    # Outro — quiet window city lights
    ("window_city", 164.0, 172.0, 1.07),
    ("window_city_b", 172.0, 180.0, 1.08),
]


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 50_000:
        log.info("cached %s", dest.name)
        return dest
    log.info("download %s → %s", url, dest.name)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)
    return dest


def fit_cover(clip, w: int = W, h: int = H):
    """Center-crop cover to w×h."""
    scale = max(w / max(clip.w, 1), h / max(clip.h, 1))
    clip = clip.resize(scale)
    x1 = max(0, int((clip.w - w) / 2))
    y1 = max(0, int((clip.h - h) / 2))
    return clip.crop(x1=x1, y1=y1, width=w, height=h)


def soft_ken_burns(clip, duration: float, zoom_end: float = 1.06):
    """Slow push-in so static stock doesn't feel frozen."""
    import numpy as np
    from PIL import Image

    duration = max(0.2, float(duration))
    zoom_end = max(1.01, float(zoom_end))
    base = clip.set_duration(duration)

    def _zoom(get_frame, t):
        frame = get_frame(t)
        img = Image.fromarray(frame)
        prog = 0.0 if duration <= 0 else min(1.0, max(0.0, float(t) / duration))
        z = 1.0 + (zoom_end - 1.0) * prog
        nw, nh = max(W, int(img.width * z)), max(H, int(img.height * z))
        img = img.resize((nw, nh), Image.LANCZOS)
        left = max(0, (nw - W) // 2)
        top = max(0, (nh - H) // 2)
        img = img.crop((left, top, left + W, top + H))
        return np.asarray(img)

    return base.fl(_zoom, apply_to=["mask"]).set_duration(duration)


def night_confession_grade(clip):
    """One LUT-ish pass: cool night, crushed blacks, light grain + vignette."""
    import numpy as np

    grain = 0.014
    vig_s = 0.22
    gamma = 0.92
    contrast = 1.08
    h, w = int(clip.h), int(clip.w)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    dist = np.sqrt(((yy - cy) / max(cy, 1.0)) ** 2 + ((xx - cx) / max(cx, 1.0)) ** 2)
    vignette = 1.0 - vig_s * np.clip((dist - 0.35) / 0.85, 0.0, 1.0) ** 1.4
    vignette = vignette.astype(np.float32)[..., None]
    power = 1.0 / max(gamma, 0.05)

    def _process(get_frame, t):
        frame = np.asarray(get_frame(t), dtype=np.float32) / 255.0
        frame = (frame - 0.5) * contrast + 0.5
        frame = np.clip(frame, 0.0, 1.0)
        frame = np.power(frame, power)
        # Cool teal lift in shadows / slightly pull reds (night confession)
        frame[..., 0] *= 0.96
        frame[..., 2] = np.clip(frame[..., 2] * 1.04, 0.0, 1.0)
        seed = int(round(float(t) * 24.0)) & 0xFFFFFFFF
        rng = np.random.default_rng(seed)
        frame = frame + rng.normal(0.0, grain, frame.shape).astype(np.float32)
        frame = frame * vignette
        return (np.clip(frame, 0.0, 1.0) * 255.0).astype(np.uint8)

    log.info("Night confession grade ON")
    return clip.fl(_process)


def plate_clip(path: Path, duration: float, zoom_end: float = 1.06):
    from moviepy.editor import VideoFileClip, concatenate_videoclips

    duration = max(0.2, float(duration))
    src = VideoFileClip(str(path)).without_audio()
    src = fit_cover(src)
    if src.duration + 0.05 >= duration:
        out = src.subclip(0, duration)
    else:
        loops = []
        filled = 0.0
        while filled < duration - 0.01:
            remain = duration - filled
            piece = src if src.duration <= remain + 0.05 else src.subclip(0, remain)
            loops.append(piece)
            filled += float(piece.duration)
        out = concatenate_videoclips(loops, method="compose")
        if out.duration > duration:
            out = out.subclip(0, duration)
    out = out.set_duration(duration)
    return soft_ken_burns(out, duration, zoom_end=zoom_end)


def assemble_picture() -> Path:
    from moviepy.editor import AudioFileClip, concatenate_videoclips

    TEMP.mkdir(parents=True, exist_ok=True)
    BROLL_DIR.mkdir(parents=True, exist_ok=True)

    # Ensure every asset used in timeline is cached
    needed = {key for key, *_ in PLATES}
    for key in needed:
        url = ASSETS[key]
        download(url, BROLL_DIR / f"{key}.mp4")

    clips = []
    for key, t0, t1, zoom in PLATES:
        clips.append(plate_clip(BROLL_DIR / f"{key}.mp4", t1 - t0, zoom_end=zoom))
    video = concatenate_videoclips(clips, method="compose")
    if video.duration > TARGET_SEC + 0.05:
        video = video.subclip(0, TARGET_SEC)
    elif video.duration < TARGET_SEC - 0.05:
        gap = TARGET_SEC - float(video.duration)
        hold = video.to_ImageClip(t=max(0, float(video.duration) - 0.04)).set_duration(gap)
        video = concatenate_videoclips([video, hold], method="compose")

    video = night_confession_grade(video)

    if not SONG.exists():
        raise FileNotFoundError(f"Master song missing: {SONG}")
    song = AudioFileClip(str(SONG))
    song = song.subclip(0, min(float(song.duration), float(video.duration), TARGET_SEC))
    video = video.set_audio(song)

    draft = TEMP / "broll_picture_audio_v2.mp4"
    log.info("writing draft %s (%.1fs, %s plates)", draft, video.duration, len(clips))
    video.write_videofile(
        str(draft),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        bitrate="12000k",
        audio_bitrate="320k",
        preset="medium",
        threads=4,
        logger=None,
    )
    video.close()
    song.close()
    for c in clips:
        try:
            c.close()
        except Exception:
            pass
    return draft


def cues_to_whisper_json(align_path: Path) -> dict:
    data = json.loads(align_path.read_text(encoding="utf-8"))
    segments = []
    for cue in data.get("cues") or []:
        text = str(cue.get("text") or "").strip()
        if not text:
            continue
        start = float(cue["start"])
        end = float(cue["end"])
        if end <= start:
            end = start + 0.4
        words = []
        karaoke = cue.get("karaoke") or []
        t = start
        if karaoke:
            for item in karaoke:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    w, dur = str(item[0]).strip(), float(item[1])
                elif isinstance(item, dict):
                    w = str(item.get("word") or item.get("text") or "").strip()
                    dur = float(item.get("duration") or item.get("dur") or 0.2)
                else:
                    continue
                if not w:
                    continue
                words.append({"word": w + " ", "start": t, "end": t + max(0.05, dur)})
                t += max(0.05, dur)
            # snap last word end to cue end
            if words:
                words[-1]["end"] = max(words[-1]["end"], end)
        segments.append({"start": start, "end": end, "text": text, "words": words})
    return {"segments": segments}


def burn_pycaps(draft: Path, out: Path, transcript: dict) -> Path:
    """Try PyCaps hype template; raises on failure."""
    from pycaps import TemplateLoader, TranscriptFormat, VideoQuality

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    tx_path = TEMP / "lyrics_whisper.json"
    tx_path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")

    builder = (
        TemplateLoader("hype")
        .with_input_video(str(draft))
        .load(should_build_pipeline=False)
    )
    builder.with_output_video(str(out))
    builder.with_transcription(transcript, format=TranscriptFormat.WHISPER_JSON)
    if CSS.exists():
        builder.add_css(str(CSS))
    try:
        builder.with_video_quality(VideoQuality.HIGH)
    except Exception:
        pass

    pipe = builder.build()
    pipe.run()
    if not out.exists():
        raise FileNotFoundError(f"PyCaps did not write {out}")
    return out


def burn_ass_fallback(draft: Path, out: Path, transcript: dict) -> Path:
    """ASS karaoke burn via ffmpeg if PyCaps fails."""
    ass_path = TEMP / "lyrics_karaoke.ass"
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Arial Black,68,&H0000CCFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,5,3,2,80,80,90,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    def ts(sec: float) -> str:
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = sec % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    for seg in transcript.get("segments") or []:
        words = seg.get("words") or []
        if not words:
            text = str(seg.get("text") or "").replace("\n", " ")
            lines.append(
                f"Dialogue: 0,{ts(float(seg['start']))},{ts(float(seg['end']))},Default,,0,0,0,,{text}"
            )
            continue
        # {\k} uses centiseconds
        parts = []
        for w in words:
            dur_cs = max(1, int(round((float(w["end"]) - float(w["start"])) * 100)))
            token = str(w["word"]).strip()
            parts.append(rf"{{\k{dur_cs}}}{token} ")
        start = float(words[0]["start"])
        end = float(words[-1]["end"])
        lines.append(
            f"Dialogue: 0,{ts(start)},{ts(end)},Default,,0,0,0,,{''.join(parts).rstrip()}"
        )

    ass_path.write_text("\n".join(lines), encoding="utf-8")
    # ffmpeg ass filter: escape Windows drive colon
    ass_filter = str(ass_path).replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(draft),
        "-vf",
        f"ass='{ass_filter}'",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-b:v",
        "12000k",
        "-c:a",
        "copy",
        str(out),
    ]
    log.info("ASS fallback: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    draft = assemble_picture()
    transcript = cues_to_whisper_json(ALIGN)
    out = OUT_DIR / "music_video_broll_lyric_I_Never_Said_It_Out.mp4"
    # ASS karaoke is the reliable premium path (gold active word, spaced lyrics).
    # PyCaps custom CSS often renders illegibly; hype template is optional polish.
    prefer_ass = True
    if prefer_ass:
        burn_ass_fallback(draft, out, transcript)
        log.info("ASS karaoke → %s (%.1f MB)", out, out.stat().st_size / 1e6)
        # Also keep a named ASS copy
        ass_copy = OUT_DIR / "music_video_broll_lyric_I_Never_Said_It_Out_ass.mp4"
        if ass_copy.resolve() != out.resolve():
            shutil.copy2(out, ass_copy)
    else:
        try:
            burn_pycaps(draft, out, transcript)
            log.info("PyCaps OK → %s (%.1f MB)", out, out.stat().st_size / 1e6)
        except Exception as exc:
            log.exception("PyCaps failed (%s) — ASS fallback", exc)
            burn_ass_fallback(draft, out, transcript)
            log.info("ASS OK → %s (%.1f MB)", out, out.stat().st_size / 1e6)
    print(f"DONE {out}")


if __name__ == "__main__":
    main()
