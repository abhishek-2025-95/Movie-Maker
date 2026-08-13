"""Night Slalom Down an Active Erupting Volcano — Extreme POV Reel.

9:16 · ~15s · Flux GGUF stills → Wan 2.2 two-pass MoE (NO LoRA)
→ Real-ESRGAN / HQ 1080×1920 · molten captions · volcanic audio bed.

External only: scripts/run_volcano_boarding_night_external.bat
"""
from __future__ import annotations

import logging
import math
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config
from comfy_runner import apply_scene_to_workflow, load_workflow, pick_best_output, run_workflow
from pipeline_wan import (
    render_scene_wan_two_pass,
    wan_quality_cfg,
    wan_quality_steps,
    write_quality_run_report,
)
from quality_os.upscale import realesrgan_available, upscale_video_to_master
from utils import apply_cinematic_layering, new_client_id, restart_comfyui

log = logging.getLogger("volcano_boarding")

WORK = ROOT / "temp" / "volcano_boarding_night"
OUT = ROOT / "final_outputs" / "Volcano_Boarding_Night_Slalom.mp4"
CAPTION_OUT = ROOT / "final_outputs" / "Volcano_Boarding_Night_Slalom_caption.txt"

STILL_W, STILL_H = 768, 1344
WW, WH = 480, 832
OUT_W, OUT_H = 1080, 1920
COOLDOWN = 12
SEED = 20260806
BITRATE = getattr(config, "EXPORT_BITRATE", "15000k")
FONT_BOLD = ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf"
WIN_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")

SCENE = (
    "cinematic 9:16 vertical video, intense action camera helmet GoPro POV, "
    "night on an active erupting volcano, pitch-black sky, hyper-realistic 4k, "
    "vivid orange and jet-black color contrast, high shutter speed, heat distortion"
)
NEG = (
    "cartoon, anime, illustration, text overlay, watermark, logo, daylight, sunny, "
    "cheerful, smiling selfie, crowd, deformed hands, extra fingers, blurry, lowres, "
    "plastic CGI, overexposed washout, comic book, LoRA artifact, soft pastel"
)

BEATS = [
    {
        "id": "b0_summit",
        "sec": 4.0,
        "length": 65,
        "caption": "Boarding down an ACTIVE volcano at night... 🌋🔥",
        "still": (
            f"{SCENE}, standing at the summit of an erupting volcano at midnight, "
            "crimson lava fountains shoot high into pitch-black sky, fiery orange glow "
            "across steep obsidian ash slopes, helmet POV looking down the drop, "
            "heat shimmer on distant magma"
        ),
        "visual": (
            f"{SCENE}, summit of erupting volcano at midnight, crimson lava fountains, "
            "fiery orange glow on steep black ash slopes, helmet POV about to drop"
        ),
        "motion": (
            "lava fountains erupt upward, ash dust drift, helmet micro-shake, "
            "glow pulsing on slopes, heat haze shimmer, rider leans toward drop"
        ),
    },
    {
        "id": "b1_carve",
        "sec": 4.0,
        "length": 65,
        "caption": "Speed: 75 MPH on pure obsidian ash.",
        "still": (
            f"{SCENE}, pushing off on a custom heat-shielded mountain board, "
            "accelerating down a 60-degree steep ash slope at 75 MPH, carving through "
            "thick black volcanic dust, helmet POV looking ahead down the mountain, "
            "lava glow rim-lighting the ash"
        ),
        "visual": (
            f"{SCENE}, helmet POV racing down steep volcanic ash slope on mountain board, "
            "black dust spray, orange lava glow, extreme speed"
        ),
        "motion": (
            "violent acceleration downslope, board carving ash, dust spray into lens, "
            "aggressive wind shake, slope rushing past, lava glow streaks"
        ),
    },
    {
        "id": "b2_magma",
        "sec": 3.0,
        "length": 49,
        "caption": "INCHES FROM 2,000°F MAGMA. 💀🔥",
        "still": (
            f"{SCENE}, navigating inches past glowing liquid red magma rivers flowing "
            "down the mountain, sparks and embers flying toward the camera lens, "
            "extreme heat distortion waves over neon-orange lava against pitch black, "
            "helmet POV extreme close pass"
        ),
        "visual": (
            f"{SCENE}, inches from glowing liquid magma river, embers and sparks toward "
            "helmet lens, intense heat haze warping air, jet-black ash vs neon orange lava"
        ),
        "motion": (
            "slow-motion ember sparks fly into lens, heat distortion shimmer warps air, "
            "board skims beside magma river, lens flare from molten red, high tension carve"
        ),
        "heat_haze": True,
    },
    {
        "id": "b3_launch",
        "sec": 4.0,
        "length": 65,
        "caption": "CLEARING THE LAVA FISSURE. 🏃‍♂️💨",
        "still": (
            f"{SCENE}, launching off a glowing lava fissure catching massive air, "
            "landing toward dark lower ash fields, volcano behind detonates into a "
            "majestic fountain of molten rock, helmet POV mid-air then landing"
        ),
        "visual": (
            f"{SCENE}, board launch over glowing lava fissure, massive air, volcano "
            "erupts behind into molten rock fountain, landing on dark ash fields"
        ),
        "motion": (
            "launch off fissure, airborne float then land clean, massive eruption boom "
            "behind, ash blast, camera shake on impact, molten fountain climax"
        ),
    },
]


def _ffprobe_dur(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return float((r.stdout or "0").strip() or 0)
    except ValueError:
        return 0.0


def _ensure_comfy() -> None:
    import urllib.request

    url = f"http://{config.COMFYUI_HOST}/system_stats"
    for attempt in range(8):
        try:
            urllib.request.urlopen(url, timeout=5)
            return
        except Exception:
            time.sleep(2.0 + attempt)
    print("COMFY_START", flush=True)
    if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
        raise RuntimeError("ComfyUI failed to start")


def _pick(prefix: str):
    best = pick_best_output([], prefix, allow_stale_disk=True)
    if best is not None:
        return best
    from comfy_runner import latest_files_with_prefix

    imgs = [
        p
        for p in latest_files_with_prefix(prefix)
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    return imgs[0] if imgs else None


def flux_still(*, prompt: str, prefix: str, dest: Path, seed: int) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 40_000:
        print(f"STILL_REUSE {dest.name}", flush=True)
        return dest

    _ensure_comfy()
    wf_path = ROOT / "workflows" / "flux_t2i_gguf_api.json"
    if not wf_path.exists():
        wf_path = config.resolve_workflow_flux()
    nm_path = ROOT / "workflows" / "node_map_flux_gguf.json"
    import json

    nm = json.loads(nm_path.read_text(encoding="utf-8")) if nm_path.exists() else config.NODE_MAP_FLUX
    wf = load_workflow(wf_path)
    job = apply_scene_to_workflow(
        wf,
        visual_prompt=prompt,
        motion_prompt="",
        filename_prefix=prefix,
        width=STILL_W,
        height=STILL_H,
        node_map=nm,
        include_motion_in_prompt=False,
        cinematic_suffix=(
            "photorealistic cinematic action sports, 4k detail, vivid orange jet-black contrast, "
            "helmet GoPro POV, no text, no watermark"
        ),
        negative_prompt=NEG,
        seed=seed,
    )
    print(f"FLUX {prefix} (no LoRA)", flush=True)
    _, paths = run_workflow(job, client_id=new_client_id(), timeout_s=2400)
    best = pick_best_output(paths, prefix, allow_stale_disk=True) or _pick(prefix)
    if not best:
        raise RuntimeError(f"Still missing: {prefix}")
    shutil.copy2(best, dest)
    print(f"STILL_OK {dest}", flush=True)
    time.sleep(COOLDOWN)
    return dest


def apply_heat_haze(src: Path, dest: Path) -> Path:
    """Subtle heat-distortion shimmer for magma beat (8–11s)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Mild horizontal wave + saturation punch toward neon orange
    vf = (
        "geq="
        "r='r(X+1.5*sin(2*PI*Y/55+T*4),Y)':"
        "g='g(X+1.5*sin(2*PI*Y/55+T*4),Y)':"
        "b='b(X+1.2*sin(2*PI*Y/55+T*4),Y)',"
        "eq=contrast=1.08:saturation=1.18:gamma=0.96,"
        "noise=alls=5:allf=t"
    )
    r = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "16",
            "-preset",
            "slow",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0 or not dest.exists():
        log.warning("heat haze failed, copying source: %s", (r.stderr or "")[-400:])
        shutil.copy2(src, dest)
    return dest


def wan_clip(still: Path, beat: dict, seed: int) -> Path:
    dest = WORK / "clips" / f"{beat['id']}_24.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 60_000 and _ffprobe_dur(dest) >= beat["sec"] - 0.4:
        print(f"WAN_REUSE {dest.name}", flush=True)
        return dest

    raw = render_scene_wan_two_pass(
        still=still,
        visual=beat["visual"],
        motion=beat["motion"],
        prefix=f"volc_{beat['id']}",
        seed=seed,
        neg=NEG,
        ww=WW,
        wh=WH,
        length=int(beat["length"]),
        work=WORK / "clips",
    )
    trimmed = WORK / "clips" / f"{beat['id']}_trim.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(raw),
            "-t",
            f"{beat['sec']:.3f}",
            "-vf",
            "fps=24,format=yuv420p",
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "16",
            "-preset",
            "slow",
            str(trimmed),
        ],
        check=True,
        capture_output=True,
    )
    if beat.get("heat_haze"):
        apply_heat_haze(trimmed, dest)
    else:
        shutil.copy2(trimmed, dest)
    print(f"WAN_OK {dest} ({_ffprobe_dur(dest):.2f}s)", flush=True)
    time.sleep(COOLDOWN)
    return dest


def stitch_hard(clips: list[Path], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    lst = WORK / "concat.txt"
    lst.write_text(
        "\n".join(f"file '{c.resolve().as_posix()}'" for c in clips) + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "24",
            "-crf",
            "16",
            "-an",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
    return dest


def _write_wav(path: Path, audio: np.ndarray, sr: int = 44100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(audio, -1.0, 1.0)
    stereo = np.column_stack([pcm, pcm * 0.98]).astype(np.float32)
    interleaved = (stereo.reshape(-1) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(interleaved.tobytes())
    return path


def _edge_yell(dest: Path) -> Path | None:
    try:
        import asyncio

        import edge_tts
    except ImportError:
        return None

    mp3 = dest.with_suffix(".mp3")

    async def _run() -> None:
        communicate = edge_tts.Communicate("YEAH!", "en-US-GuyNeural", rate="+25%", pitch="+5Hz")
        await communicate.save(str(mp3))

    try:
        asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        log.warning("edge-tts yell failed: %s", exc)
        return None
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(mp3),
            "-af",
            "volume=2.2,highpass=f=180,lowpass=f=4500,aresample=44100",
            str(dest),
        ],
        check=False,
        capture_output=True,
    )
    return dest if dest.exists() else None


def build_volcano_bed(dur: float, work: Path) -> Path:
    """Procedural bed: detonations, fire, heartbeats, ash carve, heat hiss, eruption."""
    sr = 44100
    n = int(dur * sr)
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(42)
    audio = np.zeros(n, dtype=np.float64)

    # Continuous fire crackle + wind bed
    audio += 0.018 * rng.standard_normal(n)
    audio += 0.03 * np.sin(2 * math.pi * 42 * t)
    audio += 0.012 * np.sin(2 * math.pi * 88 * t) * (0.5 + 0.5 * np.sin(2 * math.pi * 0.7 * t))

    # 0–4s: volcanic detonations + heartbeats
    for boom_t in (0.4, 1.5, 2.8, 3.6):
        c = int(boom_t * sr)
        span = int(0.35 * sr)
        if 0 <= c < n:
            x = np.linspace(0, 1, min(span, n - c))
            env = np.exp(-4.5 * x)
            audio[c : c + len(x)] += 0.55 * env * np.sin(2 * math.pi * 48 * (x * 0.35))
            audio[c : c + len(x)] += 0.25 * env * rng.standard_normal(len(x))
    for hb in (0.8, 1.6, 2.4, 3.2):
        c = int(hb * sr)
        span = int(0.12 * sr)
        if 0 <= c < n:
            x = np.linspace(0, np.pi, min(span, n - c))
            audio[c : c + len(x)] += 0.12 * np.sin(x) ** 2

    # 4–8s: board crunch gravel + violent wind
    for i in range(n):
        tt = t[i]
        if 4.0 <= tt < 8.0:
            audio[i] += 0.08 * abs(math.sin(2 * math.pi * 14 * tt)) * rng.standard_normal()
            audio[i] += 0.06 * math.sin(2 * math.pi * 220 * tt) * (0.3 + 0.7 * abs(math.sin(2 * math.pi * 9 * tt)))
            audio[i] += 0.05 * rng.standard_normal()

    # 8–11s: sub-bass heat rumble + magma hiss + ember whoosh
    for i in range(n):
        tt = t[i]
        if 8.0 <= tt < 11.0:
            audio[i] += 0.1 * math.sin(2 * math.pi * 28 * tt)
            audio[i] += 0.04 * math.sin(2 * math.pi * 3100 * tt) * (0.4 + 0.6 * abs(math.sin(2 * math.pi * 2.5 * tt)))
            audio[i] += 0.03 * rng.standard_normal()
    for whoosh in (8.4, 9.2, 10.1):
        c = int(whoosh * sr)
        span = int(0.22 * sr)
        if 0 <= c < n:
            x = np.linspace(0, 1, min(span, n - c))
            env = np.sin(np.pi * x) ** 2
            audio[c : c + len(x)] += 0.2 * env * rng.standard_normal(len(x))

    # 12–15s: eruption boom + sub drop (yell layered later)
    for i in range(n):
        tt = t[i]
        if tt >= 11.0:
            audio[i] += 0.08 * math.sin(2 * math.pi * 36 * tt) * min(1.0, (tt - 11.0) / 1.2)
            audio[i] += 0.04 * rng.standard_normal()
    boom_at = int(12.15 * sr)
    span = int(0.55 * sr)
    if boom_at < n:
        x = np.linspace(0, 1, min(span, n - boom_at))
        env = np.exp(-3.2 * x)
        audio[boom_at : boom_at + len(x)] += 0.85 * env * np.sin(2 * math.pi * 40 * (x * 0.55))
        audio[boom_at : boom_at + len(x)] += 0.4 * env * rng.standard_normal(len(x))
    # sub-bass drop
    drop_at = int(12.4 * sr)
    span = int(1.2 * sr)
    if drop_at < n:
        x = np.linspace(0, 1, min(span, n - drop_at))
        audio[drop_at : drop_at + len(x)] += 0.35 * np.exp(-2.0 * x) * np.sin(2 * math.pi * 32 * (x * 1.2))

    peak = float(np.max(np.abs(audio)) or 1.0)
    audio = 0.92 * audio / peak
    bed = work / "volcano_bed.wav"
    _write_wav(bed, audio, sr)

    yell = _edge_yell(work / "rider_yell.wav")
    mixed = work / "volcano_mix.wav"
    if yell and yell.exists():
        fc = (
            "[0:a]volume=1.0[a0];"
            "[1:a]volume=1.8,adelay=12200|12200[y];"
            "[a0][y]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        )
        r = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(bed),
                "-i",
                str(yell),
                "-filter_complex",
                fc,
                "-map",
                "[aout]",
                str(mixed),
            ],
            capture_output=True,
            check=False,
        )
        if r.returncode == 0 and mixed.exists():
            return mixed
    shutil.copy2(bed, mixed)
    return mixed


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in (FONT_BOLD, WIN_BOLD):
        if p.exists():
            return ImageFont.truetype(str(p), size=size)
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        trial = " ".join(cur + [w])
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_w or not cur:
            cur.append(w)
        else:
            lines.append(" ".join(cur))
            cur = [w]
    if cur:
        lines.append(" ".join(cur))
    return lines[:3]


def render_caption_png(text: str, w: int, h: int, dest: Path) -> Path:
    """Molten yellow-orange fiery type, ember outline, upper-center."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _font(48 if w >= 1080 else 40)
    max_w = int(w * 0.86)
    lines = _wrap(draw, text, font, max_w)
    line_h = int(font.size * 1.22)
    y0 = int(h * 0.10)
    ember = (255, 90, 20, 255)
    molten = (255, 210, 60, 255)
    for li, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2
        y = y0 + li * line_h
        # Ember glow / seismic vibration outline
        for dx, dy in (
            (-4, 0),
            (4, 0),
            (0, -4),
            (0, 4),
            (-3, -3),
            (3, 3),
            (-3, 3),
            (3, -3),
            (0, 5),
            (1, 4),
            (-1, 4),
        ):
            draw.text((x + dx, y + dy), line, font=font, fill=ember)
        draw.text((x, y), line, font=font, fill=molten)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest


def burn_captions(video: Path, audio: Path, dest: Path) -> Path:
    from moviepy.editor import AudioFileClip, CompositeVideoClip, ImageClip, VideoFileClip

    v = VideoFileClip(str(video))
    overlays = []
    cap_dir = WORK / "captions"
    t0 = 0.0
    for i, beat in enumerate(BEATS):
        dur = float(beat["sec"])
        png = render_caption_png(beat["caption"], OUT_W, OUT_H, cap_dir / f"cap_{i:02d}.png")
        # Micro seismic vibration via tiny position jitter across short subclips
        clip = (
            ImageClip(str(png))
            .set_start(t0)
            .set_duration(dur)
            .crossfadein(0.15)
            .crossfadeout(0.15)
        )
        overlays.append(clip)
        t0 += dur
    comp = CompositeVideoClip([v, *overlays], size=(OUT_W, OUT_H))
    try:
        graded = apply_cinematic_layering(comp, grade=None)
    except Exception as exc:  # noqa: BLE001
        log.warning("grade skip: %s", exc)
        graded = comp
    a = AudioFileClip(str(audio)).subclip(0, min(graded.duration, _ffprobe_dur(audio)))
    out = graded.set_audio(a)
    out.write_videofile(
        str(dest),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        bitrate=BITRATE,
        preset="slow",
        ffmpeg_params=["-pix_fmt", "yuv420p"],
        logger=None,
    )
    out.close()
    v.close()
    a.close()
    return dest


def write_caption_file() -> None:
    text = (
        "75 MPH. 2,000°F molten lava rivers. One wrong edge-turn and you melt. 🌋🔥⚡\n\n"
        "Night-boarding down an active erupting cone is the ultimate combination of extreme "
        "speed and raw planetary power. The heat waves radiant off those magma channels will "
        "melt your face off.\n\n"
        "Drop a 🔥 in the comments if this made your heart race! 👇\n\n"
        "#AdrenalineRush #VolcanoBoarding #LavaSlalom #ExtremeSports #POV #NightRush "
        "#ThrillSeeker #Redline #GoProPOV #ExtremeHeat\n"
    )
    CAPTION_OUT.write_text(text, encoding="utf-8")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    WORK.mkdir(parents=True, exist_ok=True)
    (ROOT / "final_outputs").mkdir(parents=True, exist_ok=True)
    config.refresh_workflow_paths()

    steps = wan_quality_steps()
    cfg = wan_quality_cfg()
    print("=== Volcano Boarding Night Slalom (NO LoRA) ===", flush=True)
    print(
        f"QUALITY flux_steps={getattr(config, 'FLUX_STEPS', 24)} wan_steps={steps} wan_cfg={cfg} "
        f"still={STILL_W}x{STILL_H} wan={WW}x{WH} master={OUT_W}x{OUT_H} "
        f"realesrgan={realesrgan_available()} beats={len(BEATS)} two_pass=True lora=False",
        flush=True,
    )
    print("FLUX", config.resolve_workflow_flux().name, config.gguf_flux_ready(), flush=True)
    print("WAN", config.resolve_workflow_wan().name, config.gguf_wan_ready(), flush=True)

    if not config.gguf_flux_ready() or not config.gguf_wan_ready():
        raise RuntimeError("GGUF Flux/Wan not ready — enable USE_GGUF_5070_PROFILE and models")

    assert getattr(config, "QUALITY_FIRST", False), "QUALITY_FIRST must be True"
    if steps < 14:
        raise RuntimeError(f"Wan steps {steps} < 14 — quality floor violated")

    plates: dict[str, Path] = {}
    for i, beat in enumerate(BEATS):
        plates[beat["id"]] = flux_still(
            prompt=beat["still"],
            prefix=f"volc_plate_{beat['id']}",
            dest=WORK / "stills" / f"{beat['id']}.png",
            seed=SEED + i * 97,
        )

    clips: list[Path] = []
    beat_meta = []
    for i, beat in enumerate(BEATS):
        print(f"\n=== BEAT {i+1}/{len(BEATS)} {beat['id']} two_pass ===", flush=True)
        clip = wan_clip(plates[beat["id"]], beat, SEED + 1000 + i * 41)
        clips.append(clip)
        beat_meta.append(
            {
                "id": beat["id"],
                "dur": _ffprobe_dur(clip),
                "wan_wh": [WW, WH],
                "length": beat["length"],
                "two_pass": True,
                "lora": False,
                "heat_haze": bool(beat.get("heat_haze")),
            }
        )

    rough = WORK / "rough_480.mp4"
    stitch_hard(clips, rough)
    print(f"STITCH_OK {rough} ({_ffprobe_dur(rough):.2f}s)", flush=True)

    hq = WORK / "hq_1080.mp4"
    print("UPSCALE_REALESRGAN" if realesrgan_available() else "UPSCALE_HQ_FALLBACK", flush=True)
    upscale_video_to_master(rough, hq, out_w=OUT_W, out_h=OUT_H)
    print(f"UPSCALE_OK {hq} {OUT_W}x{OUT_H}", flush=True)

    bed = build_volcano_bed(_ffprobe_dur(hq), WORK / "audio")
    print(f"AUDIO_OK {bed}", flush=True)

    print("CAPTIONS_MOLTEN_UPPER_CENTER", flush=True)
    burn_captions(hq, bed, OUT)
    write_caption_file()

    report = write_quality_run_report(
        WORK,
        smoke="volcano_boarding_night",
        topic="Night Slalom Down an Active Erupting Volcano",
        niche="Volcano Boarding / Extreme Heat Sports / Lava Slalom POV",
        beats=beat_meta,
        lora=False,
        realesrgan=realesrgan_available(),
        captions="molten_yellow_orange_ember_outline_upper_center",
        output=str(OUT),
        output_wh=[OUT_W, OUT_H],
        output_duration_s=_ffprobe_dur(OUT),
        output_bytes=OUT.stat().st_size if OUT.exists() else 0,
    )
    print(f"REPORT {report}", flush=True)
    print(f"FINAL {OUT} ({_ffprobe_dur(OUT):.2f}s) bytes={OUT.stat().st_size}", flush=True)
    print(f"CAPTION_FILE {CAPTION_OUT}", flush=True)
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
