"""US Brooklyn Stoop — The Almost (10.0s cinematic romance).

Latest Quality OS path on RTX 5070 12GB:
  Flux GGUF hero still (24 steps) → optional IP-Adapter plates →
  Wan 2.2 two-pass MoE (steps ≥14, CFG 4.5) → short xfade →
  Real-ESRGAN or sleep317-class 1920×1080 grade → real music/Foley bed.

Hero-plate lock: one two-shot still; every Wan beat starts from that plate
(or an IP-Adapter / crop of those same pixels). No freeze-pad. No Ken Burns.

External:
  scripts/run_us_stoop_almost_10s_external.bat
  scripts/run_us_stoop_almost_10s_external.sh
"""
from __future__ import annotations

import json
import logging
import math
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
from comfy_runner import (
    apply_scene_to_workflow,
    load_workflow,
    pick_best_output,
    run_workflow,
)
from pipeline_wan import (
    render_scene_wan_two_pass,
    should_use_two_pass,
    wan_quality_cfg,
    wan_quality_steps,
    write_quality_run_report,
)
from quality_os.preflight import check_p1, ipadapter_workflow_ready
from quality_os.upscale import realesrgan_available, upscale_video_to_master
from utils import (
    apply_cinematic_layering,
    comfyui_reachable,
    free_comfyui_memory,
    new_client_id,
    restart_comfyui,
    wait_comfy_healthy,
)

log = logging.getLogger("us_stoop_10s")

WORK = ROOT / "temp" / "us_stoop_almost_10s_v2"
OUT = ROOT / "final_outputs" / "US_Brooklyn_Stoop_Almost_10s_v2.mp4"

# 16:9 cinematic master — US film-short, not a vertical reel
STILL_W, STILL_H = 1344, 768
WW, WH = 832, 480
OUT_W, OUT_H = 1920, 1080
WAN_FPS = 16.0
WAN_LEN = 81  # 5.0625s @ 16fps (proven 12GB two-pass length)
XFADE_SEC = 0.125  # 2×5.0625 − 0.125 = 10.000s
TARGET_SEC = 10.0
COOLDOWN = 12
SEED = 20260814
BITRATE = getattr(config, "EXPORT_BITRATE", "15000k")
PREFIX = "stoop10v2"

WOMAN = (
    "same young Black American woman every frame identity lock: mid-20s, warm brown skin, "
    "dark natural curls in a stable halo not crawling, small gold hoop earrings, "
    "white linen sundress, hazel-brown eyes, soft rose lips, SAME FACE every frame"
)
MAN = (
    "same young Black American man every frame identity lock: late-20s, CLEAN-SHAVEN "
    "no beard no mustache no stubble, short cropped hair, blue chambray shirt sleeves rolled, "
    "kind dark brown eyes, SAME FACE every frame"
)
SCENE = (
    "cinematic 16:9 photoreal 35mm, Brooklyn brownstone stoop late August golden hour, "
    "pink hydrangeas, honey backlight, quiet residential street bokeh, shallow depth of field, "
    "warm tungsten bounce from brownstone brick, faces sharp readable, locked-off tripod"
)
LOCK = (
    f"exactly these two people only: ({WOMAN}) and ({MAN}), contemporary New York summer, "
    "sitting close on the stoop, US independent-film romance, no modern logos"
)
NEG = (
    config.FLUX_NEGATIVE_PROMPT
    + ", beard, mustache, stubble, cartoon, anime, text, watermark, extra people, crowd, "
    "looking at camera, smile at viewer, kissing, lips touching, cheek to cheek, "
    "whispering into ear, faces overlapping, motion blur, ghosting, double exposure, "
    "extra head, second face overlay, melted face, identity morph, deformed hands, "
    "extra fingers, handheld shake, camera push-in, zoom, smear"
)

HERO_PROMPT = (
    f"{LOCK}, {SCENE}, stable medium two-shot 35mm, BOTH faces fully visible with a clear "
    "six-inch air gap between noses, NOT touching, NOT cheek to cheek, looking at each other, "
    "lips clearly apart, her hand and his hand rest on the brownstone step between them "
    "clearly readable fingers almost touching, hydrangeas left, honey flare right, "
    "sharp faces identity locked, no ghosting"
)

BEATS = [
    {
        "id": "b0_hold",
        "plate": "hero",
        "length": WAN_LEN,
        "cut_in": "start",
        "visual": HERO_PROMPT + ", locked-off hold, golden hour stillness, faces sharp",
        "motion": (
            "LOCKED-OFF tripod camera NO push-in NO handheld, only tiny blinks and chest breath, "
            "hydrangea petals barely drift, faces stay in the exact same place identity locked, "
            "no morph no ghosting no smear"
        ),
    },
    {
        "id": "b1_hands",
        "plate": "continue",
        "length": WAN_LEN,
        "cut_in": "xfade",
        "visual": (
            HERO_PROMPT + ", same framing same faces, only his fingers slowly closer to hers "
            "on the stoop, faces still separated by air, sharp"
        ),
        "motion": (
            "LOCKED-OFF tripod SAME framing NO zoom, only his fingers inch toward hers on the stone, "
            "tiny blinks, faces do not drift, no wind in hair, no morph no ghosting no smear"
        ),
    },
]


def planned_duration_sec(*, n_beats: int = 2, length: int = WAN_LEN, xfade: float = XFADE_SEC) -> float:
    """Stitched coverage with one xfade between beats. No freeze-pad."""
    shot = length / WAN_FPS
    if n_beats <= 1:
        return shot
    return n_beats * shot - (n_beats - 1) * xfade


def quality_lock() -> dict:
    """Hard quality-first contract for this 10s piece."""
    return {
        "quality_first": bool(getattr(config, "QUALITY_FIRST", False)),
        "two_pass": should_use_two_pass(),
        "wan_steps": wan_quality_steps(),
        "wan_cfg": wan_quality_cfg(),
        "flux_steps": int(getattr(config, "FLUX_STEPS", 0)),
        "freeze_pad": bool(getattr(config, "QUALITY_ALLOW_FREEZE_PAD", True)),
        "ken_burns": bool(getattr(config, "QUALITY_ALLOW_KEN_BURNS_FALLBACK", True)),
        "target_sec": TARGET_SEC,
        "planned_sec": planned_duration_sec(),
        "master_wh": [OUT_W, OUT_H],
        "wan_wh": [WW, WH],
        "aspect": "16:9",
        "audience": "US",
    }


def assert_quality_lock() -> dict:
    q = quality_lock()
    if not q["quality_first"]:
        raise RuntimeError("QUALITY_FIRST must be True")
    if not q["two_pass"]:
        raise RuntimeError("Wan must use two-pass MoE")
    if q["wan_steps"] < 14:
        raise RuntimeError(f"Wan steps {q['wan_steps']} < 14")
    if q["wan_cfg"] < 4.0:
        raise RuntimeError(f"Wan CFG {q['wan_cfg']} < 4.0")
    if q["flux_steps"] < 22:
        raise RuntimeError(f"Flux steps {q['flux_steps']} < 22")
    if q["freeze_pad"]:
        raise RuntimeError("Freeze-pad is forbidden")
    if q["ken_burns"]:
        raise RuntimeError("Ken Burns fallback is forbidden")
    if abs(q["planned_sec"] - TARGET_SEC) > 0.05:
        raise RuntimeError(f"Beat plan {q['planned_sec']:.3f}s != {TARGET_SEC}s")
    return q


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


def _ensure_comfy(*, restart: bool = False) -> None:
    """Use a healthy Comfy if it's already up. Do not kill a working instance.

    The previous path always kill-restarted at job start. That dropped the
    user's running Comfy and often relaunched it with the wrong Python
    (system 3.11 instead of Comfy's python_embeded), so /system_stats never
    came back.
    """
    if comfyui_reachable() and not restart:
        print("COMFY_UP — using already-running instance (skip kill)", flush=True)
        free_comfyui_memory()
        return
    if comfyui_reachable() and restart:
        print("COMFY_RESTART", flush=True)
        if restart_comfyui(wait_sec=180) or wait_comfy_healthy(wait_sec=60, progress=True):
            print("COMFY_HEALTHY", flush=True)
            return
        if comfyui_reachable():
            print("COMFY_UP_AFTER_WAIT", flush=True)
            return
        raise RuntimeError(
            "ComfyUI did not come back after restart. Start it with your usual "
            "ComfyUI bat (keep that window open), then re-run this script."
        )
    print("COMFY_START — API down. Opening a VISIBLE ComfyUI window.", flush=True)
    print("If no new window appears, start ComfyUI yourself (run_nvidia_gpu.bat) and wait.", flush=True)
    launched = restart_comfyui(wait_sec=180)
    if launched or wait_comfy_healthy(wait_sec=90, progress=True):
        print("COMFY_HEALTHY", flush=True)
        return
    raise RuntimeError(
        "ComfyUI is not reachable at 127.0.0.1:8188. Start it first with your "
        "usual Comfy launcher (C:\\ComfyUI\\run_nvidia_gpu.bat), wait until the "
        "browser UI loads, KEEP THAT WINDOW OPEN, then re-run "
        "scripts\\run_us_stoop_almost_10s_external.bat"
    )


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


def _stage_flux_ref(src: Path, dest_name: str) -> str:
    """Copy identity still at native Flux size (do not downscale to Wan canvas)."""
    from PIL import Image

    config.COMFYUI_INPUT.mkdir(parents=True, exist_ok=True)
    dest = config.COMFYUI_INPUT / dest_name
    Image.open(src).convert("RGB").save(dest, format="PNG")
    return dest_name


def flux_still(
    *,
    prompt: str,
    prefix: str,
    dest: Path,
    seed: int,
    reference: Path | None = None,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 80_000:
        print(f"STILL_REUSE {dest.name}", flush=True)
        return dest

    _ensure_comfy()
    use_ipa = reference is not None and ipadapter_workflow_ready()
    if use_ipa:
        wf_path = ROOT / "workflows" / "flux_t2i_ipadapter_gguf_api.json"
        nm_path = ROOT / "workflows" / "node_map_flux_ipadapter_gguf.json"
        nm = json.loads(nm_path.read_text(encoding="utf-8")) if nm_path.exists() else config.NODE_MAP_FLUX
        ref_name = _stage_flux_ref(reference, f"{PREFIX}_{prefix}_ref.png")
        print(f"FLUX_IPA {prefix} ref={ref_name} steps={config.FLUX_STEPS}", flush=True)
    else:
        wf_path = ROOT / "workflows" / "flux_t2i_gguf_api.json"
        if not wf_path.exists():
            wf_path = config.resolve_workflow_flux()
        nm_path = ROOT / "workflows" / "node_map_flux_gguf.json"
        nm = json.loads(nm_path.read_text(encoding="utf-8")) if nm_path.exists() else config.NODE_MAP_FLUX
        ref_name = None
        print(f"FLUX_HERO {prefix} steps={config.FLUX_STEPS}", flush=True)

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


def make_plates(hero: Path) -> dict[str, Path]:
    """Same-pixel identity plates via crop of the hero two-shot."""
    from PIL import Image

    plates_dir = WORK / "plates"
    plates_dir.mkdir(parents=True, exist_ok=True)
    im = Image.open(hero).convert("RGB")
    w, h = im.size
    out: dict[str, Path] = {"hero": hero}

    tight = plates_dir / "hero_tight.png"
    if not (tight.exists() and tight.stat().st_size > 20_000):
        m = int(min(w, h) * 0.10)
        im.crop((m, m, w - m, h - m)).resize((w, h), Image.LANCZOS).save(tight, format="PNG")
    out["hero_tight"] = tight
    return out


def _xfade_pair(a: Path, b: Path, dest: Path, overlap: float) -> Path:
    d0 = _ffprobe_dur(a)
    offset = max(0.05, d0 - overlap)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(a),
            "-i",
            str(b),
            "-filter_complex",
            f"[0:v][1:v]xfade=transition=fade:duration={overlap:.3f}:offset={offset:.3f}[v]",
            "-map",
            "[v]",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "16",
            "-preset",
            "slow",
            "-r",
            "24",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
    return dest


def _extract_last_frame(mp4: Path, png: Path) -> Path:
    """Continuation plate: last pixels of the previous Wan clip, same geometry."""
    png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-sseof",
            "-0.08",
            "-i",
            str(mp4),
            "-frames:v",
            "1",
            str(png),
        ],
        check=True,
        capture_output=True,
    )
    if not png.exists() or png.stat().st_size < 1000:
        raise RuntimeError(f"last-frame extract failed: {mp4}")
    return png


def _piano_note(t: np.ndarray, f0: float, t0: float, dur: float, amp: float) -> np.ndarray:
    """Struck harmonic tone (decay envelope) — not a held placeholder sine."""
    rel = np.maximum(t - t0, 0.0)
    gate = (t >= t0) & (t < t0 + dur)
    env = np.exp(-rel / max(0.12, dur * 0.28)) * gate
    hammer = np.exp(-rel / 0.012) * gate
    sig = np.zeros_like(t)
    for k, a in ((1, 1.00), (2, 0.42), (3, 0.18), (4, 0.09), (5, 0.04)):
        sig += a * np.sin(2 * np.pi * f0 * k * t)
    noise = 0.15 * np.random.default_rng(int(f0 * 10) + int(t0 * 1000)).standard_normal(t.size)
    return amp * (sig * env + noise * hammer)


def build_romance_bed(dur: float, dest: Path) -> Path:
    """Warm US-summer score: piano voicing + pad + street Foley + almost-touch heartbeat.

    Not a single placeholder sine. Mix is stereo WAV for the 10s master.
    """
    sr = 44100
    n = int(math.ceil(dur * sr))
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(20260813)
    audio = np.zeros(n, dtype=np.float64)

    # Distant Brooklyn evening: low rumble + air
    audio += 0.018 * rng.standard_normal(n)
    audio += 0.012 * np.sin(2 * np.pi * 48 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.12 * t))
    # Light summer air / leaves
    audio += 0.006 * np.sin(2 * np.pi * 9.0 * t) * rng.standard_normal(n)

    # Warm pad (slow Cmaj7 → Am) under the piano
    pad_env = np.clip(t / 1.4, 0, 1) * np.clip((dur - t) / 1.6, 0, 1)
    pad = (
        0.035 * np.sin(2 * np.pi * 130.81 * t)
        + 0.028 * np.sin(2 * np.pi * 164.81 * t)
        + 0.022 * np.sin(2 * np.pi * 196.00 * t)
        + 0.016 * np.sin(2 * np.pi * 246.94 * t)
    )
    # Slow detune chorus
    pad += 0.012 * np.sin(2 * np.pi * 131.4 * t + 0.4 * np.sin(2 * np.pi * 0.2 * t))
    audio += pad * pad_env

    # Piano-like voicing across the 10s (C – E – G – B then A – C – E)
    notes = [
        (261.63, 0.15, 1.8, 0.11),
        (329.63, 0.55, 1.6, 0.09),
        (392.00, 1.05, 1.7, 0.08),
        (493.88, 1.70, 2.0, 0.07),
        (220.00, 3.10, 2.2, 0.10),
        (261.63, 3.55, 1.8, 0.08),
        (329.63, 4.15, 1.9, 0.07),
        (392.00, 5.05, 2.4, 0.09),
        (329.63, 6.20, 2.2, 0.10),
        (493.88, 6.85, 2.6, 0.11),
        (523.25, 8.10, 2.4, 0.09),
        (392.00, 8.70, 2.2, 0.07),
    ]
    for f0, t0, nd, amp in notes:
        audio += _piano_note(t, f0, t0, nd, amp)

    # Fabric / stone Foley around the almost-touch
    for t0, amp in ((5.85, 0.045), (6.35, 0.06), (6.9, 0.04)):
        c = int(t0 * sr)
        span = int(0.18 * sr)
        if 0 <= c < n:
            end = min(n, c + span)
            rustle = rng.standard_normal(end - c) * np.hanning(end - c)
            audio[c:end] += amp * rustle

    # Heartbeat cue as fingers almost meet
    for beat_t in (6.15, 6.88, 7.62):
        c = int(beat_t * sr)
        span = int(0.14 * sr)
        if 0 <= c < n:
            end = min(n, c + span)
            x = np.linspace(0, np.pi, end - c)
            audio[c:end] += 0.055 * (np.sin(x) ** 2)

    pcm = np.nan_to_num(np.clip(audio, -0.95, 0.95), nan=0.0)
    # Gentle stereo: pad a hair left, piano slightly right
    left = pcm * 0.98
    right = np.roll(pcm, 18) * 1.00
    stereo = np.column_stack([left, right]).reshape(-1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((stereo * 32767.0).astype(np.int16).tobytes())
    return dest


def mux_grade(video: Path, audio: Path, dest: Path) -> Path:
    from moviepy.editor import AudioFileClip, VideoFileClip

    v = VideoFileClip(str(video))
    a = AudioFileClip(str(audio))
    end = min(float(v.duration), float(a.duration), TARGET_SEC)
    v = v.subclip(0, end)
    a = a.subclip(0, end)
    try:
        graded = apply_cinematic_layering(v, grade="music_soft")
    except Exception as exc:  # noqa: BLE001
        log.warning("grade skip: %s", exc)
        graded = v
    out = graded.set_audio(a)
    dest.parent.mkdir(parents=True, exist_ok=True)
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


def render_beat(plate: Path, beat: dict, seed: int) -> Path:
    clean = WORK / "clips" / f"{beat['id']}_24.mp4"
    clean.parent.mkdir(parents=True, exist_ok=True)
    want = beat["length"] / WAN_FPS
    if clean.exists() and clean.stat().st_size > 80_000 and _ffprobe_dur(clean) >= want - 0.35:
        print(f"WAN_REUSE {clean.name}", flush=True)
        return clean

    print(
        f"WAN {beat['id']} plate={plate.name} {WW}x{WH} len={beat['length']} "
        f"steps={wan_quality_steps()} cfg={wan_quality_cfg()}",
        flush=True,
    )
    raw = render_scene_wan_two_pass(
        still=plate,
        visual=beat["visual"],
        motion=beat["motion"],
        prefix=f"{PREFIX}_{beat['id']}",
        seed=seed,
        neg=NEG,
        ww=WW,
        wh=WH,
        length=int(beat["length"]),
        work=WORK / "clips",
    )
    # Conform to 24fps. Trim only — never freeze-pad.
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(raw),
            "-t",
            f"{want:.4f}",
            "-vf",
            "fps=24,format=yuv420p",
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "16",
            "-preset",
            "slow",
            str(clean),
        ],
        check=True,
        capture_output=True,
    )
    print(f"WAN_OK {clean} ({_ffprobe_dur(clean):.2f}s)", flush=True)
    time.sleep(COOLDOWN)
    return clean


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    log_path = WORK / "run.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )
    (ROOT / "final_outputs").mkdir(parents=True, exist_ok=True)
    config.refresh_workflow_paths()

    q = assert_quality_lock()
    pf = check_p1(require_realesrgan=False, require_ipadapter=False)
    ipa = ipadapter_workflow_ready()
    esr = realesrgan_available()
    print("=== US Brooklyn Stoop — The Almost v2 (anti-shake) ===", flush=True)
    print(f"QUALITY {json.dumps(q)}", flush=True)
    print(f"PREFLIGHT ipadapter={ipa} realesrgan={esr} notes={pf.notes}", flush=True)
    print("FLUX", config.resolve_workflow_flux().name, config.gguf_flux_ready(), flush=True)
    print("WAN", config.resolve_workflow_wan().name, config.gguf_wan_ready(), flush=True)
    print(f"FORMAT 16:9 still={STILL_W}x{STILL_H} wan={WW}x{WH} master={OUT_W}x{OUT_H}", flush=True)

    if not config.gguf_flux_ready() or not config.gguf_wan_ready():
        raise RuntimeError(
            "GGUF Flux/Wan not ready. This job needs the RTX 5070 ComfyUI stack "
            "(flux1-dev-Q5_K_S + Wan 2.2 MoE Q4 two-pass)."
        )

    print("COMFY_PREFLIGHT", flush=True)
    _ensure_comfy(restart=False)

    hero = flux_still(
        prompt=HERO_PROMPT,
        prefix=f"{PREFIX}_hero",
        dest=WORK / "stills" / "hero.png",
        seed=SEED,
        reference=None,
    )
    if ipa:
        print("IPA_HERO refine (same prompt, no new angle)", flush=True)
        hero = flux_still(
            prompt=HERO_PROMPT,
            prefix=f"{PREFIX}_hero_ipa",
            dest=WORK / "stills" / "hero_ipa.png",
            seed=SEED + 3,
            reference=hero,
        )

    plates = {"hero": hero}
    print("PLATES", {k: v.name for k, v in plates.items()}, flush=True)

    clips: list[Path] = []
    beat_meta = []
    continue_png = hero
    for i, beat in enumerate(BEATS):
        print(f"\n=== BEAT {i+1}/{len(BEATS)} {beat['id']} two_pass plate={beat['plate']} ===", flush=True)
        if beat["plate"] == "continue":
            plate = continue_png
        else:
            plate = plates.get(beat["plate"], hero)
        clip = render_beat(plate, beat, SEED + 1000 + i * 41)
        clips.append(clip)
        continue_png = _extract_last_frame(clip, WORK / "chunks" / f"{beat['id']}_last.png")
        beat_meta.append(
            {
                "id": beat["id"],
                "dur": _ffprobe_dur(clip),
                "wan_wh": [WW, WH],
                "two_pass": True,
                "length": beat["length"],
                "plate": beat["plate"],
            }
        )

    silent = WORK / "rough_480.mp4"
    if len(clips) == 1:
        shutil.copy2(clips[0], silent)
    else:
        _xfade_pair(clips[0], clips[1], silent, XFADE_SEC)
    print(f"STITCH_OK {silent} ({_ffprobe_dur(silent):.2f}s)", flush=True)

    hq = WORK / "hq_1080.mp4"
    print("UPSCALE_REALESRGAN" if esr else "UPSCALE_HQ_CHAIN", flush=True)
    upscale_video_to_master(silent, hq, out_w=OUT_W, out_h=OUT_H)
    print(f"UPSCALE_OK {hq} {OUT_W}x{OUT_H}", flush=True)

    bed = build_romance_bed(max(TARGET_SEC, _ffprobe_dur(hq)) + 0.05, WORK / "audio" / "bed.wav")
    print(f"AUDIO_OK {bed} ({_ffprobe_dur(bed):.2f}s)", flush=True)
    mux_grade(hq, bed, OUT)

    dur = _ffprobe_dur(OUT)
    report = write_quality_run_report(
        WORK,
        smoke="us_stoop_almost_10s_v2",
        topic="Brooklyn Stoop — The Almost",
        niche="Heart-flutter romance / US cinematic short",
        audience="US",
        beats=beat_meta,
        ipadapter=ipa,
        realesrgan=esr,
        captions="none",
        audio="piano_foley_heartbeat_bed",
        freeze_pad=False,
        output=str(OUT),
        output_wh=[OUT_W, OUT_H],
        output_duration_s=dur,
        output_bytes=OUT.stat().st_size if OUT.exists() else 0,
        planned_sec=planned_duration_sec(),
        target_sec=TARGET_SEC,
    )
    print(f"REPORT {report}", flush=True)
    print(f"FINAL {OUT} ({dur:.2f}s) bytes={OUT.stat().st_size}", flush=True)
    if abs(dur - TARGET_SEC) > 0.45:
        log.warning("duration %.2fs off target %.1fs (no freeze-pad)", dur, TARGET_SEC)
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"FATAL {exc}", flush=True)
        raise SystemExit(1)
