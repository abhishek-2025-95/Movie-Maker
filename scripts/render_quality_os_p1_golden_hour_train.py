"""Quality OS P1 — Golden Hour Train Connection (external).

P1 path: Flux identity bible → Flux IP-Adapter locked stills → Wan two-pass
→ hard stitch → Real-ESRGAN 1080×1920 → premium upper-third captions + audio.

Topic: Heart-Fluttering Romance / Cozy POV — The Golden Hour Train Connection
External: scripts/run_quality_os_p1_golden_hour_train_external.bat
"""
from __future__ import annotations

import logging
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
from comfy_runner import (
    apply_scene_to_workflow,
    load_workflow,
    pick_best_output,
    run_workflow,
    stage_reference_image,
)
from pipeline_wan import (
    render_scene_wan_two_pass,
    wan_quality_cfg,
    wan_quality_steps,
    write_quality_run_report,
)
from quality_os.preflight import check_p1
from quality_os.upscale import realesrgan_available, upscale_video_to_master
from utils import apply_cinematic_layering, new_client_id, restart_comfyui

log = logging.getLogger("qos_p1_train")

WORK = ROOT / "temp" / "quality_os_p1_golden_hour_train"
OUT = ROOT / "final_outputs" / "Quality_OS_P1_Golden_Hour_Train.mp4"

# 9:16 vertical delivery
STILL_W, STILL_H = 768, 1344
WW, WH = 480, 832
OUT_W, OUT_H = 1080, 1920
COOLDOWN = 12
SEED = 20260805
BITRATE = getattr(config, "EXPORT_BITRATE", "15000k")
SERIF_BOLD = Path(r"C:\Windows\Fonts\georgiab.ttf")
SERIF = Path(r"C:\Windows\Fonts\georgia.ttf")
FALLBACK_FONT = ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf"

SCENE = (
    "cinematic 9:16 vertical, quiet commuter train interior at golden hour, "
    "warm dreamlike sunlight streaming through train windows, soft lens flare, "
    "wooden window-ledge table, hyper-realistic 35mm film aesthetic, shallow depth of field"
)
WOMAN = (
    "same young woman every frame identity lock: mid-20s East Asian woman, soft oval face, "
    "warm brown eyes, natural freckles, dark wavy hair half-loose, cream knit sweater, "
    "wireless earbud in one ear, cozy romantic POV heroine"
)
GUY = (
    "same young man every frame identity lock: mid-20s man, soft warm smile, gentle eyes, "
    "short dark hair, light linen shirt under charcoal jacket, sitting across the aisle, "
    "kind unhurried energy"
)
NEG = (
    "cartoon, anime, text overlay, watermark, logo, deformed hands, extra fingers, "
    "blurry, lowres, overexposed, selfie, crowd, multiple faces overlapping, "
    "ugly, distorted face, plastic skin, CGI"
)

# Absolute caption windows (seconds) — premium on-screen copy (no emoji for clean burn)
CAPTIONS = [
    (0.0, 3.0, "I fell asleep on the train and dropped my earbud…"),
    (3.0, 6.0, "He didn't wake me up, but he left this note."),
    (6.0, 10.0, "HE WAS LISTENING TO THE SAME SONG."),
    (10.0, 15.0, "Slide left to see what I typed on my phone screen!"),
]

BEATS = [
    {
        "id": "b0_sleep",
        "ref": "woman",
        "length": 65,  # ~4.06s
        "visual": (
            f"{SCENE}, {WOMAN}, close-up resting her head against the cool window glass, "
            f"half-asleep, phone on the window-ledge table showing a music player UI, "
            f"one wireless earbud falling into her lap, warm rim light on cheek"
        ),
        "motion": (
            "subtle breathing, head soft against glass, earbud drops into lap, "
            "golden light shifts slowly, handheld micro-sway, faces sharp"
        ),
    },
    {
        "id": "b1_note",
        "ref": "guy",
        "length": 65,
        "visual": (
            f"{SCENE}, {GUY}, {WOMAN} softly asleep across from him blurred background, "
            f"he gently picks up the dropped earbud from her lap, places it on the wooden table, "
            f"leaves a tiny handwritten sticky note with clearly legible English words: "
            f"'Your playlist has immaculate taste. Track 3 was my favorite.', "
            f"focus on his careful hands and the note"
        ),
        "motion": (
            "gentle hand reach, careful pick up earbud, place sticky note, "
            "soft smile, train micro-shake, warm light flicker"
        ),
    },
    {
        "id": "b2_awake",
        "ref": "woman",
        "length": 65,
        "visual": (
            f"{SCENE}, {WOMAN} stirs awake as train jostles, sees the sticky note, "
            f"blushes instantly reading clearly legible handwriting, looks up to see {GUY} "
            f"smiling softly holding up his phone playing the same song, "
            f"rack focus from note to his soft smile, butterfly moment"
        ),
        "motion": (
            "soft stir awake, eyes open to note, blush, look up, "
            "focus pull from note to his smile, phone screen glow, slow push-in"
        ),
    },
    {
        "id": "b3_reply",
        "ref": "woman",
        "length": 49,  # ~3.06s
        "visual": (
            f"{SCENE}, {WOMAN} takes a breath, opens Notes app on phone, types a shy reply, "
            f"slides the phone across the wooden table toward {GUY} with a timid "
            f"heart-fluttering smile, golden hour flare, intimate two-shot"
        ),
        "motion": (
            "typing thumbs, timid smile, phone slides across table, "
            "soft laughter breath, warm flare bloom, hold"
        ),
    },
]


def _ffprobe_dur(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", str(path),
        ],
        capture_output=True, text=True, check=False,
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
        p for p in latest_files_with_prefix(prefix)
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    return imgs[0] if imgs else None


def flux_still(
    *,
    prompt: str,
    prefix: str,
    dest: Path,
    seed: int,
    reference: Path | None = None,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 40_000:
        print(f"STILL_REUSE {dest.name}", flush=True)
        return dest

    _ensure_comfy()
    if reference is not None:
        wf_path = ROOT / "workflows" / "flux_t2i_ipadapter_gguf_api.json"
        nm = config.NODE_MAP_FLUX
        ref_name = stage_reference_image(reference, f"qos_p1_{prefix}_ref.png")
        print(f"FLUX_IPA {prefix} ref={ref_name}", flush=True)
    else:
        # Identity bible: plain GGUF (no IP-Adapter required)
        wf_path = ROOT / "workflows" / "flux_t2i_gguf_api.json"
        if not wf_path.exists():
            wf_path = config.resolve_workflow_flux()
        nm_path = ROOT / "workflows" / "node_map_flux_gguf.json"
        nm = __import__("json").loads(nm_path.read_text(encoding="utf-8")) if nm_path.exists() else config.NODE_MAP_FLUX
        ref_name = None
        print(f"FLUX_BIBLE {prefix}", flush=True)

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
        cinematic_suffix=config.STYLE_SUFFIX.get("live", config.CINEMATIC_SUFFIX),
        negative_prompt=NEG,
        seed=seed,
        reference_image_name=ref_name,
    )
    _, paths = run_workflow(job, client_id=new_client_id(), timeout_s=2400)
    best = pick_best_output(paths, prefix, allow_stale_disk=True) or _pick(prefix)
    if not best:
        raise RuntimeError(f"Still missing: {prefix}")
    shutil.copy2(best, dest)
    print(f"STILL_OK {dest}", flush=True)
    time.sleep(COOLDOWN)
    return dest


def stitch_hard(clips: list[Path], dest: Path) -> Path:
    lst = WORK / "concat.txt"
    lst.write_text(
        "\n".join(f"file '{c.resolve().as_posix()}'" for c in clips) + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "24", "-crf", "16",
            "-an", str(dest),
        ],
        check=True,
        capture_output=True,
    )
    return dest


def audio_bed(dur: float, dest: Path) -> Path:
    """Train hum → muffled acoustic → full warm swell (procedural stand-in)."""
    sr = 44100
    n = int(dur * sr)
    t = np.arange(n) / sr
    # rhythmic rail clack + low hum
    rail = 0.04 * np.sin(2 * np.pi * 3.2 * t) * np.sin(2 * np.pi * 90 * t)
    hum = 0.025 * np.sin(2 * np.pi * 55 * t) + 0.015 * np.sin(2 * np.pi * 110 * t)
    wind = 0.008 * np.random.randn(n)
    # warm acoustic-ish chord (muffled early, crisp later)
    guitar = (
        0.03 * np.sin(2 * np.pi * 196 * t)
        + 0.025 * np.sin(2 * np.pi * 247 * t)
        + 0.02 * np.sin(2 * np.pi * 294 * t)
    )
    env = np.ones(n)
    # 0–3s: mostly rails; 3–6s: muffled guitar; 6–10s: crisp; 10–end: swell
    for i, ti in enumerate(t):
        if ti < 3.0:
            env[i] = 0.15
        elif ti < 6.0:
            env[i] = 0.45
        elif ti < 10.0:
            env[i] = 0.85
        else:
            env[i] = 1.0
    # soft heartbeat cue ~6–8s
    hb = np.zeros(n)
    for beat_t in (6.2, 6.95, 7.7):
        c = int(beat_t * sr)
        if 0 <= c < n:
            span = int(0.12 * sr)
            x = np.linspace(0, np.pi, span)
            pulse = 0.06 * np.sin(x) ** 2
            end = min(n, c + span)
            hb[c:end] += pulse[: end - c]
    audio = rail + hum + wind + guitar * env + hb
    pcm = np.clip(audio.astype(np.float64), -1, 1)
    stereo = np.column_stack([pcm, pcm * 0.98]).reshape(-1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((stereo * 32767.0).astype(np.int16).tobytes())
    return dest


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in (SERIF_BOLD, SERIF, FALLBACK_FONT):
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
    """Premium upper-third caption: warm cream on soft dark plate — bright + clear."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _font(52 if w >= 1080 else 44)
    max_w = int(w * 0.86)
    lines = _wrap(draw, text, font, max_w)
    line_h = int(font.size * 1.28)
    block_h = line_h * len(lines) + 36
    block_w = max_w + 48
    # Upper third — soft dark plate so cream stays bright on golden-hour plates
    x0 = (w - block_w) // 2
    y0 = int(h * 0.10)
    plate = Image.new("RGBA", (block_w, block_h), (0, 0, 0, 0))
    pd = ImageDraw.Draw(plate)
    pd.rounded_rectangle(
        [0, 0, block_w - 1, block_h - 1],
        radius=22,
        fill=(18, 10, 6, 168),
    )
    img.alpha_composite(plate, (x0, y0))

    cream = (255, 245, 220, 255)  # warm cream — bright
    outline = (20, 12, 8, 255)
    y = y0 + 18
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2
        # soft outline for premium clarity (not muddy)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            draw.text((x + dx, y + dy), line, font=font, fill=outline)
        draw.text((x, y), line, font=font, fill=cream)
        y += line_h
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest


def burn_captions(video: Path, dest: Path, duration: float) -> Path:
    from moviepy.editor import CompositeVideoClip, ImageClip, VideoFileClip

    v = VideoFileClip(str(video))
    overlays = []
    cap_dir = WORK / "captions"
    for i, (t0, t1, text) in enumerate(CAPTIONS):
        if t0 >= duration:
            continue
        end = min(t1, duration)
        png = render_caption_png(text, OUT_W, OUT_H, cap_dir / f"cap_{i:02d}.png")
        clip = (
            ImageClip(str(png))
            .set_start(t0)
            .set_duration(max(0.05, end - t0))
            .crossfadein(0.35)
            .crossfadeout(0.30)
        )
        overlays.append(clip)
    comp = CompositeVideoClip([v, *overlays], size=(OUT_W, OUT_H))
    bed = audio_bed(duration + 0.05, WORK / "audio" / "bed.wav")
    from moviepy.editor import AudioFileClip

    a = AudioFileClip(str(bed)).subclip(0, min(comp.duration, _ffprobe_dur(bed)))
    try:
        graded = apply_cinematic_layering(comp, grade="music_soft")
    except Exception as exc:  # noqa: BLE001
        log.warning("grade skip: %s", exc)
        graded = comp
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


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    WORK.mkdir(parents=True, exist_ok=True)
    (ROOT / "final_outputs").mkdir(parents=True, exist_ok=True)
    config.refresh_workflow_paths()

    assert getattr(config, "QUALITY_FIRST", False), "QUALITY_FIRST must be True"
    assert not getattr(config, "QUALITY_ALLOW_FREEZE_PAD", True)
    assert getattr(config, "EXPORT_USE_REALESRGAN", False), "EXPORT_USE_REALESRGAN must be True"

    pf = check_p1()
    print(f"PREFLIGHT {pf}", flush=True)
    if not pf.ok:
        raise RuntimeError(f"P1 preflight failed: {pf.missing}")

    steps = wan_quality_steps()
    cfg = wan_quality_cfg()
    print("=== Quality OS P1 — Golden Hour Train Connection ===", flush=True)
    print("FLUX", config.resolve_workflow_flux().name, flush=True)
    print("WAN", config.resolve_workflow_wan().name, flush=True)
    print(
        f"QUALITY flux_steps={config.FLUX_STEPS} wan_steps={steps} wan_cfg={cfg} "
        f"still={STILL_W}x{STILL_H} wan={WW}x{WH} master={OUT_W}x{OUT_H} "
        f"realesrgan={realesrgan_available()} beats={len(BEATS)}",
        flush=True,
    )
    if not config.gguf_flux_ready() or not config.gguf_wan_ready():
        raise RuntimeError("GGUF Flux/Wan not ready")

    # Fresh Comfy so hung queue / VRAM from prior run is cleared
    print("COMFY_RESTART_FOR_P1", flush=True)
    restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120)))

    woman = flux_still(
        prompt=f"{SCENE}, {WOMAN}, portrait medium close-up seated by train window, golden hour",
        prefix="qos_p1_id_woman",
        dest=WORK / "stills" / "id_woman.png",
        seed=SEED,
        reference=None,
    )
    guy = flux_still(
        prompt=f"{SCENE}, {GUY}, portrait medium close-up seated across aisle, golden hour",
        prefix="qos_p1_id_guy",
        dest=WORK / "stills" / "id_guy.png",
        seed=SEED + 7,
        reference=None,
    )
    refs = {"woman": woman, "guy": guy}

    # IP-Adapter locked beat plates
    plates: dict[str, Path] = {}
    for i, beat in enumerate(BEATS):
        ref = refs[beat["ref"]]
        plates[beat["id"]] = flux_still(
            prompt=beat["visual"],
            prefix=f"qos_p1_plate_{beat['id']}",
            dest=WORK / "stills" / f"{beat['id']}.png",
            seed=SEED + 100 + i * 17,
            reference=ref,
        )

    clips: list[Path] = []
    beat_meta = []
    for i, beat in enumerate(BEATS):
        clean = WORK / "clips" / f"{beat['id']}_24.mp4"
        print(f"\n=== BEAT {i+1}/{len(BEATS)} {beat['id']} two_pass ===", flush=True)
        if clean.exists() and clean.stat().st_size > 50_000 and _ffprobe_dur(clean) > 1.5:
            print(f"BEAT_REUSE {clean} ({_ffprobe_dur(clean):.2f}s)", flush=True)
        else:
            # Drop partials from a hung prior pass
            for stale in (WORK / "clips").glob(f"qos_p1_{beat['id']}*"):
                try:
                    stale.unlink()
                except OSError:
                    pass
            out = render_scene_wan_two_pass(
                still=plates[beat["id"]],
                visual=beat["visual"],
                motion=beat["motion"],
                prefix=f"qos_p1_{beat['id']}",
                seed=SEED + 1000 + i * 41,
                neg=NEG,
                ww=WW,
                wh=WH,
                length=int(beat["length"]),
                work=WORK / "clips",
            )
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(out),
                    "-vf", "fps=24,format=yuv420p",
                    "-an", "-c:v", "libx264", "-crf", "16", "-preset", "slow",
                    str(clean),
                ],
                check=True,
                capture_output=True,
            )
            print(f"BEAT_OK {clean} ({_ffprobe_dur(clean):.2f}s)", flush=True)
            time.sleep(COOLDOWN)
        clips.append(clean)
        dur = _ffprobe_dur(clean)
        beat_meta.append(
            {
                "id": beat["id"],
                "dur": dur,
                "wan_wh": [WW, WH],
                "two_pass": True,
                "ipadapter_ref": beat["ref"],
            }
        )

    rough = WORK / "rough_480.mp4"
    stitch_hard(clips, rough)
    print(f"STITCH_OK {rough} ({_ffprobe_dur(rough):.2f}s)", flush=True)

    hq = WORK / "hq_1080.mp4"
    print("UPSCALE_REALESRGAN" if realesrgan_available() else "UPSCALE_HQ_FALLBACK", flush=True)
    upscale_video_to_master(rough, hq, out_w=OUT_W, out_h=OUT_H)
    print(f"UPSCALE_OK {hq} {OUT_W}x{OUT_H}", flush=True)

    print("CAPTIONS_PREMIUM_UPPER_THIRD", flush=True)
    burn_captions(hq, OUT, _ffprobe_dur(hq))

    report = write_quality_run_report(
        WORK,
        smoke="p1_golden_hour_train",
        topic="The Golden Hour Train Connection",
        niche="Heart-Fluttering Romance / Cozy POV",
        beats=beat_meta,
        ipadapter=True,
        realesrgan=realesrgan_available(),
        captions="premium_cream_upper_third",
        output=str(OUT),
        output_wh=[OUT_W, OUT_H],
        output_duration_s=_ffprobe_dur(OUT),
        output_bytes=OUT.stat().st_size if OUT.exists() else 0,
    )
    print(f"REPORT {report}", flush=True)
    print(f"FINAL {OUT} ({_ffprobe_dur(OUT):.2f}s) bytes={OUT.stat().st_size}", flush=True)
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
