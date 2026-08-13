"""Quality OS P0 — COMPLETE best-quality smoke (external).

Exercises the full quality-first path:
  Flux Q5 @ FLUX_STEPS → hero plate + crops
  → pipeline_wan.two_pass (steps≥14, CFG 4.5) × 3 beats
  → hard stitch (no freeze-pad)
  → editor HQ 1080 upscale chain
  → cinematic grade + audio bed
  → quality_run_report.json + final MP4

External: scripts/run_quality_os_p0_smoke_external.bat
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
from utils import apply_cinematic_layering, new_client_id, restart_comfyui

log = logging.getLogger("qos_smoke")

WORK = ROOT / "temp" / "quality_os_p0_smoke"
OUT = ROOT / "final_outputs" / "Quality_OS_P0_Complete_Smoke.mp4"

# 16:9 cinematic delivery
STILL_W, STILL_H = 1344, 768
WW, WH = 832, 480
OUT_W, OUT_H = 1920, 1080
WAN_LEN = 65  # ~4.06s @ 16fps — real motion, no freeze-pad
COOLDOWN = 10
SEED = 20260805
BITRATE = getattr(config, "EXPORT_BITRATE", "15000k")

LOCK = (
    "same woman every frame identity lock: late-20s East Asian woman, sharp cheekbones, "
    "dark wet hair in low bun, charcoal wool coat, silver hoop earrings, intense brown eyes"
)
SCENE = (
    "cinematic 16:9 night city alley after rain, neon reflections on wet asphalt, "
    "shallow depth of field, 35mm film, photorealistic, high detail faces"
)
NEG = (
    "cartoon, anime, text, watermark, logo, deformed hands, extra fingers, blurry, "
    "lowres, overexposed, smiling selfie, crowd, multiple faces"
)

BEATS = [
    {
        "id": "b0_arrive",
        "plate": "hero",
        "visual": f"{SCENE}, {LOCK}, medium shot walking toward camera under neon",
        "motion": "slow walk forward, subtle coat sway, rain streaks, handheld micro-shake, faces sharp",
    },
    {
        "id": "b1_close",
        "plate": "hero_tight",
        "visual": f"{SCENE}, {LOCK}, close-up face neon rim light, rain on lashes",
        "motion": "almost still, soft blink, breath fog, neon flicker, camera slowly pushes in",
    },
    {
        "id": "b2_turn",
        "plate": "hero_side",
        "visual": f"{SCENE}, {LOCK}, three-quarter turn looking back over shoulder, alley depth",
        "motion": "slow look-back turn, coat collar shift, rain, tense hold at end",
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

    try:
        urllib.request.urlopen(f"{config.COMFYUI_URL}/system_stats", timeout=3)
        return
    except Exception:
        pass
    print("COMFY_START", flush=True)
    if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
        raise RuntimeError("ComfyUI failed to start")


def flux_hero() -> Path:
    dest = WORK / "stills" / "hero.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 40_000:
        print(f"STILL_REUSE {dest.name}", flush=True)
        return dest
    _ensure_comfy()
    wf = load_workflow(config.resolve_workflow_flux())
    prompt = (
        f"{SCENE}, {LOCK}, hero establishing medium shot, walking into frame, "
        f"wet coat detail, cinematic color grade"
    )
    job = apply_scene_to_workflow(
        wf,
        visual_prompt=prompt,
        motion_prompt="",
        filename_prefix="qos_p0_hero",
        width=STILL_W,
        height=STILL_H,
        node_map=config.NODE_MAP_FLUX,
        include_motion_in_prompt=False,
        cinematic_suffix=config.STYLE_SUFFIX["live"],
        negative_prompt=NEG,
        seed=SEED,
    )
    print(f"FLUX_HERO steps={getattr(config, 'FLUX_STEPS', 24)}", flush=True)
    _, paths = run_workflow(job, client_id=new_client_id(), timeout_s=2400)
    best = pick_best_output(paths, "qos_p0_hero", allow_stale_disk=True)
    if best is None:
        from comfy_runner import latest_files_with_prefix

        imgs = [
            p for p in latest_files_with_prefix("qos_p0_hero")
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ]
        best = imgs[0] if imgs else None
    if not best:
        raise RuntimeError("Hero still missing")
    shutil.copy2(best, dest)
    print(f"HERO_OK {dest}", flush=True)
    time.sleep(COOLDOWN)
    return dest


def make_plates(hero: Path) -> dict[str, Path]:
    from PIL import Image

    plates_dir = WORK / "plates"
    plates_dir.mkdir(parents=True, exist_ok=True)
    im = Image.open(hero).convert("RGB")
    w, h = im.size
    out: dict[str, Path] = {"hero": hero}

    def save_crop(name: str, box: tuple[int, int, int, int]) -> Path:
        p = plates_dir / f"{name}.png"
        if not (p.exists() and p.stat().st_size > 20_000):
            im.crop(box).resize((w, h), Image.LANCZOS).save(p, format="PNG")
        out[name] = p
        return p

    m = int(min(w, h) * 0.10)
    save_crop("hero_tight", (m, m, w - m, h - m))
    dx = int(w * 0.10)
    save_crop("hero_side", (dx, 0, w, h))
    return out


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
    sr = 44100
    n = int(dur * sr)
    t = np.arange(n) / sr
    audio = (
        0.03 * np.sin(2 * np.pi * 55 * t)
        + 0.02 * np.sin(2 * np.pi * 110 * t)
        + 0.01 * np.random.randn(n)
    ).astype(np.float64)
    # soft rain-ish high hiss
    audio += 0.008 * np.random.randn(n)
    pcm = np.clip(audio, -1, 1)
    stereo = np.column_stack([pcm, pcm]).reshape(-1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((stereo * 32767.0).astype(np.int16).tobytes())
    return dest


def mux(video: Path, audio: Path, dest: Path) -> Path:
    from moviepy.editor import AudioFileClip, VideoFileClip

    v = VideoFileClip(str(video))
    try:
        v = apply_cinematic_layering(v, grade="music_soft")
    except Exception as exc:  # noqa: BLE001
        log.warning("cinematic layering skipped: %s", exc)
    a = AudioFileClip(str(audio)).subclip(0, min(v.duration, _ffprobe_dur(audio)))
    out = v.set_audio(a)
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
    assert not getattr(config, "QUALITY_ALLOW_KEN_BURNS_FALLBACK", True)

    steps = wan_quality_steps()
    cfg = wan_quality_cfg()
    print("=== Quality OS P0 COMPLETE SMOKE ===", flush=True)
    print("FLUX", config.resolve_workflow_flux().name, config.gguf_flux_ready(), flush=True)
    print("WAN", config.resolve_workflow_wan().name, config.gguf_wan_ready(), flush=True)
    print(
        f"QUALITY flux_steps={config.FLUX_STEPS} wan_steps={steps} wan_cfg={cfg} "
        f"still={STILL_W}x{STILL_H} wan={WW}x{WH} master={OUT_W}x{OUT_H} beats={len(BEATS)}",
        flush=True,
    )
    if not config.gguf_flux_ready() or not config.gguf_wan_ready():
        raise RuntimeError("GGUF Flux/Wan not ready")

    hero = flux_hero()
    plates = make_plates(hero)
    print("PLATES", {k: v.name for k, v in plates.items()}, flush=True)

    clips: list[Path] = []
    beat_meta = []
    for i, beat in enumerate(BEATS):
        print(f"\n=== BEAT {i+1}/{len(BEATS)} {beat['id']} two_pass ===", flush=True)
        plate = plates[beat["plate"]]
        out = render_scene_wan_two_pass(
            still=plate,
            visual=beat["visual"],
            motion=beat["motion"],
            prefix=f"qos_{beat['id']}",
            seed=SEED + 1000 + i * 41,
            neg=NEG,
            ww=WW,
            wh=WH,
            length=WAN_LEN,
            work=WORK / "clips",
        )
        # Re-encode to 24fps for clean stitch (no freeze-pad)
        clean = WORK / "clips" / f"{beat['id']}_24.mp4"
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
        clips.append(clean)
        dur = _ffprobe_dur(clean)
        beat_meta.append({"id": beat["id"], "dur": dur, "wan_wh": [WW, WH], "two_pass": True})
        print(f"BEAT_OK {clean} ({dur:.2f}s)", flush=True)
        time.sleep(COOLDOWN)

    rough = WORK / "rough_480.mp4"
    stitch_hard(clips, rough)
    print(f"STITCH_OK {rough} ({_ffprobe_dur(rough):.2f}s)", flush=True)

    hq = WORK / "hq_1080.mp4"
    # Silent rough → direct HQ chain (editor._ffmpeg_upscale assumes audio track)
    print("UPSCALE_HQ_CHAIN", flush=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(rough),
            "-vf",
            f"scale={OUT_W}:{OUT_H}:flags=lanczos,"
            f"eq=contrast=1.08:brightness=-0.02:saturation=0.92:gamma=0.95,"
            f"unsharp=3:3:0.55:3:3:0.0,noise=alls=6:allf=t",
            "-an", "-c:v", "libx264", "-preset", "slow", "-b:v", BITRATE,
            "-pix_fmt", "yuv420p", "-r", "24", str(hq),
        ],
        check=True,
        capture_output=True,
    )
    print(f"UPSCALE_OK {hq} {OUT_W}x{OUT_H}", flush=True)

    bed = audio_bed(_ffprobe_dur(hq) + 0.05, WORK / "audio" / "bed.wav")
    mux(hq, bed, OUT)

    report = write_quality_run_report(
        WORK,
        smoke="complete_p0",
        beats=beat_meta,
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
