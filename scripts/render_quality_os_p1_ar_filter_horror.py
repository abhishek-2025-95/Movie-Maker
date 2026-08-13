"""Quality OS P1 — The Filter That Knows Your Reflection (external).

Flux identity + IP-Adapter → Wan two-pass ×5 → Real-ESRGAN 1080×1920
→ stark horror captions (white/red upper-third) + thriller audio bed.

External: scripts/run_quality_os_p1_ar_filter_horror_external.bat
"""
from __future__ import annotations

import logging
import json
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
from quality_os.character_lora import DEFAULT_TRIGGER, lora_ready
from quality_os.preflight import check_p1
from quality_os.upscale import realesrgan_available, upscale_video_to_master
from utils import apply_cinematic_layering, new_client_id, restart_comfyui

log = logging.getLogger("qos_p2_ar_horror")

WORK = ROOT / "temp" / "quality_os_p2_ar_filter_horror"
OUT = ROOT / "final_outputs" / "Quality_OS_P2_AR_Filter_Horror_LoRA.mp4"

STILL_W, STILL_H = 768, 1344
WW, WH = 480, 832
OUT_W, OUT_H = 1080, 1920
COOLDOWN = 12
SEED = 20260806
BITRATE = getattr(config, "EXPORT_BITRATE", "15000k")
FONT_BOLD = ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf"
WIN_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")

SCENE = (
    "cinematic 9:16 vertical found-footage, extremely low-light bedroom bathroom at 3AM, "
    "dark atmospheric grain, sharp contrast shadows, realistic film noir grading, "
    "hyper-realistic 4k, handheld smartphone POV energy"
)
VIEWER = (
    f"{DEFAULT_TRIGGER}, same young adult every frame identity lock: mid-20s person, "
    f"tired pale face, dark circles under eyes, messy dark hair, oversized dark hoodie, "
    f"holding modern smartphone, scared but curious expression"
)
FIGURE = (
    "distinct shadowy humanoid figure with elongated thin limbs, obscured faceless head, "
    "wrong proportions, standing behind the viewer only inside the phone camera reflection, "
    "not a costume, uncanny horror entity"
)
NEG = (
    "cartoon, anime, watermark, logo, deformed hands, extra fingers, blurry, lowres, "
    "bright daylight, cheerful, smiling selfie influencer, crowd, jump scare clown, "
    "gore puddle, blood spray, plastic CGI skin, text overlay on walls"
)

CAPTIONS = [
    (0.0, 3.0, "This new AR filter was supposed to be just a glitchy joke…", False),
    (3.0, 6.0, "I decided to take one last burst photo.", False),
    (6.0, 9.0, "I SAW IT IN THE REFLECTION. BEHIND ME.", True),
    (9.0, 12.0, "I turned around. Empty. Was I just tired?", False),
    (12.0, 15.5, "I LOOKED BACK AT THE SCREEN. IT TOUCHED MY REFLECTION.", True),
]

BEATS = [
    {
        "id": "b0_filter",
        "length": 49,
        "visual": (
            f"{SCENE}, {VIEWER}, over-shoulder shot of modern smartphone pointed at bathroom mirror, "
            f"native camera app UI visible on phone screen with Live Face Distortion AR filter active, "
            f"digital noise mapped over their face on the phone display only, dim night ambience, "
            f"realistic phone bezels and camera interface, face lit by phone screen glow"
        ),
        "motion": (
            "subtle handheld shake, slow breathing, phone screen glow flicker, "
            "AR filter digital noise crawls on face on screen, mirror reflection steady"
        ),
    },
    {
        "id": "b1_burst",
        "length": 49,
        "visual": (
            f"{SCENE}, {VIEWER}, close on phone screen during burst photo capture, "
            f"through the phone camera lens ONLY: {FIGURE} standing right behind them in the "
            f"mirror reflection, obscured face pressed against their reflection's back, "
            f"shutter flash freeze-frames the anomaly on screen, real room behind phone looks normal"
        ),
        "motion": (
            "burst shutter clicks, phone screen flash, figure appears only on phone display, "
            "micro freeze on capture, digital glitch artifacts"
        ),
    },
    {
        "id": "b2_turn",
        "length": 49,
        "visual": (
            f"{SCENE}, {VIEWER} panics and turns around rapidly from the mirror into the empty bedroom, "
            f"nothing behind them, dark empty room, fear on face, phone still in hand, "
            f"no figure in real space, oppressive silence"
        ),
        "motion": (
            "fast whip pan turn, body spin, empty room reveal, "
            "handheld whoosh, settle on empty darkness, tense hold"
        ),
    },
    {
        "id": "b3_screen",
        "length": 49,
        "visual": (
            f"{SCENE}, {VIEWER} looks back at phone screen relieved then shaken, "
            f"AR filter glitches map over their face AND over empty air where the figure stood, "
            f"new burst photo on screen shows {FIGURE} now touching their reflection's arm, "
            f"phone UI looks authentic native camera app"
        ),
        "motion": (
            "look down to phone, screen glitch intensifies, "
            "figure hand touches reflection arm on display, static flicker"
        ),
    },
    {
        "id": "b4_touch",
        "length": 49,
        "visual": (
            f"{SCENE}, {VIEWER} realizes the mistake as a sudden cold painful grip clamps onto "
            f"their actual real arm in physical space, total panic, phone drops slightly, "
            f"aggressive camera shake, eyes wide, film noir horror climax"
        ),
        "motion": (
            "violent handheld camera shake, arm jerked, panic stumble, "
            "phone whip, abrupt freeze sting at end"
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
        ref_name = stage_reference_image(reference, f"qos_arh_{prefix}_ref.png")
        print(f"FLUX_IPA {prefix} ref={ref_name}", flush=True)
    else:
        wf_path = ROOT / "workflows" / "flux_t2i_gguf_api.json"
        if not wf_path.exists():
            wf_path = config.resolve_workflow_flux()
        nm_path = ROOT / "workflows" / "node_map_flux_gguf.json"
        nm = json.loads(nm_path.read_text(encoding="utf-8")) if nm_path.exists() else config.NODE_MAP_FLUX
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
    """Digital hum → shutters → vacuum/tinnitus → static/heartbeat → sting."""
    sr = 44100
    n = int(dur * sr)
    t = np.arange(n) / sr
    audio = np.zeros(n, dtype=np.float64)
    # persistent digital hum + breath
    audio += 0.03 * np.sin(2 * np.pi * 60 * t)
    audio += 0.012 * np.sin(2 * np.pi * 120 * t)
    audio += 0.006 * np.random.randn(n)
    breath = 0.015 * np.sin(2 * np.pi * 0.35 * t) * np.sin(2 * np.pi * 180 * t)
    audio += breath
    # 3–6s shutter clicks
    for click_t in (3.2, 3.55, 3.9, 4.25, 4.6, 5.0):
        c = int(click_t * sr)
        if 0 <= c < n - 200:
            click = np.sin(2 * np.pi * 2200 * np.linspace(0, 0.01, 200)) * np.linspace(0.2, 0, 200)
            audio[c : c + 200] += click
            audio[c : c + 400] += 0.04 * np.random.randn(min(400, n - c)) * np.linspace(1, 0, min(400, n - c))
    # 6–9s vacuum + tinnitus
    for i, ti in enumerate(t):
        if 6.0 <= ti < 9.0:
            audio[i] *= 0.25
            audio[i] += 0.04 * np.sin(2 * np.pi * 7800 * ti)
        if 6.1 <= ti < 6.4:
            audio[i] += 0.08 * np.sin(2 * np.pi * 90 * (ti - 6.1)) * np.exp(-8 * (ti - 6.1))
    # 9–12s static + heartbeats
    for i, ti in enumerate(t):
        if 9.0 <= ti < 12.0:
            audio[i] += 0.05 * np.random.randn() * ((ti - 9.0) / 3.0)
    for beat_t in (9.4, 10.2, 11.0, 11.7):
        c = int(beat_t * sr)
        span = int(0.1 * sr)
        if 0 <= c < n:
            x = np.linspace(0, np.pi, min(span, n - c))
            audio[c : c + len(x)] += 0.09 * np.sin(x) ** 2
    # 12–15s wet rustle + feedback + thud
    for i, ti in enumerate(t):
        if ti >= 12.0:
            audio[i] += 0.04 * np.random.randn()
            audio[i] += 0.05 * np.sin(2 * np.pi * 3200 * ti) * min(1.0, (ti - 12.0) / 1.5)
    thud_at = int(14.2 * sr)
    if thud_at < n - 800:
        thud = np.sin(2 * np.pi * 55 * np.linspace(0, 0.15, 800)) * np.linspace(0.5, 0, 800)
        audio[thud_at : thud_at + 800] += thud
    pcm = np.clip(audio, -1, 1)
    stereo = np.column_stack([pcm, pcm * 0.97]).reshape(-1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((stereo * 32767.0).astype(np.int16).tobytes())
    return dest


def _font(size: int) -> ImageFont.FreeTypeFont:
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


def render_caption_png(text: str, w: int, h: int, dest: Path, *, warning: bool) -> Path:
    """Stark white + red warning accent, upper third, heavy dark plate — bright & clear."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _font(50 if w >= 1080 else 42)
    max_w = int(w * 0.88)
    lines = _wrap(draw, text, font, max_w)
    line_h = int(font.size * 1.25)
    block_h = line_h * len(lines) + 44
    block_w = max_w + 56
    x0 = (w - block_w) // 2
    y0 = int(h * 0.09)
    plate = Image.new("RGBA", (block_w, block_h), (0, 0, 0, 0))
    pd = ImageDraw.Draw(plate)
    pd.rounded_rectangle([0, 0, block_w - 1, block_h - 1], radius=10, fill=(0, 0, 0, 200))
    if warning:
        pd.rectangle([0, 0, 8, block_h - 1], fill=(220, 30, 40, 255))
    img.alpha_composite(plate, (x0, y0))

    fill = (255, 255, 255, 255)
    outline = (0, 0, 0, 255)
    y = y0 + 18
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2
        for dx, dy in (
            (-3, 0), (3, 0), (0, -3), (0, 3),
            (-2, -2), (2, 2), (-2, 2), (2, -2),
            (0, 4), (0, 5),
        ):
            draw.text((x + dx, y + dy), line, font=font, fill=outline)
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest


def burn_captions(video: Path, dest: Path, duration: float) -> Path:
    from moviepy.editor import AudioFileClip, CompositeVideoClip, ImageClip, VideoFileClip

    v = VideoFileClip(str(video))
    overlays = []
    cap_dir = WORK / "captions"
    for i, (t0, t1, text, warning) in enumerate(CAPTIONS):
        if t0 >= duration:
            continue
        end = min(t1, duration)
        png = render_caption_png(text, OUT_W, OUT_H, cap_dir / f"cap_{i:02d}.png", warning=warning)
        clip = (
            ImageClip(str(png))
            .set_start(t0)
            .set_duration(max(0.05, end - t0))
            .crossfadein(0.25)
            .crossfadeout(0.25)
        )
        overlays.append(clip)
    comp = CompositeVideoClip([v, *overlays], size=(OUT_W, OUT_H))
    bed = audio_bed(duration + 0.05, WORK / "audio" / "bed.wav")
    a = AudioFileClip(str(bed)).subclip(0, min(comp.duration, _ffprobe_dur(bed)))
    try:
        graded = apply_cinematic_layering(comp, grade=None)
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

    assert getattr(config, "QUALITY_FIRST", False)
    assert not getattr(config, "QUALITY_ALLOW_FREEZE_PAD", True)
    assert getattr(config, "EXPORT_USE_REALESRGAN", False)

    pf = check_p1()
    print(f"PREFLIGHT {pf}", flush=True)
    if not pf.ok:
        raise RuntimeError(f"P1 preflight failed: {pf.missing}")
    if not lora_ready():
        raise RuntimeError(
            "P2 LoRA missing: C:\\ComfyUI\\models\\loras\\dxc_arviewer.safetensors — "
            "finish bible + scripts/run_p2_train_character_lora_external.bat first"
        )
    print(f"LORA_OK trigger={DEFAULT_TRIGGER}", flush=True)

    steps = wan_quality_steps()
    cfg = wan_quality_cfg()
    print("=== Quality OS P2 - AR Filter Horror + LoRA ===", flush=True)
    print(
        f"QUALITY flux_steps={config.FLUX_STEPS} wan_steps={steps} wan_cfg={cfg} "
        f"still={STILL_W}x{STILL_H} wan={WW}x{WH} master={OUT_W}x{OUT_H} "
        f"realesrgan={realesrgan_available()} beats={len(BEATS)}",
        flush=True,
    )
    if not config.gguf_flux_ready() or not config.gguf_wan_ready():
        raise RuntimeError("GGUF Flux/Wan not ready")

    print("COMFY_RESTART_FOR_P1", flush=True)
    restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120)))

    viewer = flux_still(
        prompt=(
            f"{SCENE}, {VIEWER}, medium close-up portrait in dark bathroom, "
            f"phone screen glow on face, 3AM found-footage"
        ),
        prefix="qos_arh_id_viewer",
        dest=WORK / "stills" / "id_viewer.png",
        seed=SEED,
        reference=None,
    )

    plates: dict[str, Path] = {}
    for i, beat in enumerate(BEATS):
        plates[beat["id"]] = flux_still(
            prompt=beat["visual"],
            prefix=f"qos_arh_plate_{beat['id']}",
            dest=WORK / "stills" / f"{beat['id']}.png",
            seed=SEED + 100 + i * 19,
            reference=viewer,
        )

    clips: list[Path] = []
    beat_meta = []
    for i, beat in enumerate(BEATS):
        clean = WORK / "clips" / f"{beat['id']}_24.mp4"
        print(f"\n=== BEAT {i+1}/{len(BEATS)} {beat['id']} two_pass ===", flush=True)
        if clean.exists() and clean.stat().st_size > 50_000 and _ffprobe_dur(clean) > 1.5:
            print(f"BEAT_REUSE {clean} ({_ffprobe_dur(clean):.2f}s)", flush=True)
        else:
            for stale in (WORK / "clips").glob(f"qos_arh_{beat['id']}*"):
                try:
                    stale.unlink()
                except OSError:
                    pass
            out = render_scene_wan_two_pass(
                still=plates[beat["id"]],
                visual=beat["visual"],
                motion=beat["motion"],
                prefix=f"qos_arh_{beat['id']}",
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
        beat_meta.append(
            {
                "id": beat["id"],
                "dur": _ffprobe_dur(clean),
                "wan_wh": [WW, WH],
                "two_pass": True,
                "ipadapter_ref": "viewer",
            }
        )

    rough = WORK / "rough_480.mp4"
    stitch_hard(clips, rough)
    print(f"STITCH_OK {rough} ({_ffprobe_dur(rough):.2f}s)", flush=True)

    hq = WORK / "hq_1080.mp4"
    print("UPSCALE_REALESRGAN" if realesrgan_available() else "UPSCALE_HQ_FALLBACK", flush=True)
    upscale_video_to_master(rough, hq, out_w=OUT_W, out_h=OUT_H)
    print(f"UPSCALE_OK {hq} {OUT_W}x{OUT_H}", flush=True)

    print("CAPTIONS_HORROR_UPPER_THIRD", flush=True)
    burn_captions(hq, OUT, _ffprobe_dur(hq))

    report = write_quality_run_report(
        WORK,
        smoke="p1_ar_filter_horror",
        topic="The Filter That Knows Your Reflection",
        niche="Modern Smartphone Horror / AR / Psychological Thriller",
        beats=beat_meta,
        ipadapter=True,
        realesrgan=realesrgan_available(),
        captions="stark_white_red_warning_upper_third",
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
