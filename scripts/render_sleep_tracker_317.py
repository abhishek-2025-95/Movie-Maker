"""The 3:17 AM Sleep-Tracker Recording — Smart-Tech Horror Reel.

9:16 · ~15s · Flux GGUF stills → Wan 2.2 two-pass → 1080×1920 master
with neon-cyan captions + procedural/Edge-TTS horror audio bed.

External only: scripts/run_sleep_tracker_317_external.bat
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config
from comfy_runner import apply_scene_to_workflow, load_workflow, pick_best_output, run_workflow
from utils import new_client_id, restart_comfyui
from wan_two_pass_moe import two_pass_wan

log = logging.getLogger("sleep317")

WORK = ROOT / "temp" / "sleep_tracker_317"
OUT = ROOT / "final_outputs" / "Sleep_Tracker_317_Horror.mp4"
CAPTION_OUT = ROOT / "final_outputs" / "Sleep_Tracker_317_caption.txt"

# 9:16 vertical
STILL_W, STILL_H = 768, 1344
WW, WH = 480, 832
OUT_W, OUT_H = 1080, 1920
WAN_LEN = 49  # ~3.06s @ 16fps
WAN_STEPS = 14
WAN_CFG = 4.5
SEED0 = 3170317
COOLDOWN = 10
BITRATE = "15000k"

ROOM = (
    "first-person POV from a person sitting up in bed at night, dark modern bedroom, "
    "rumpled sheets, nightstand, phone in hands in foreground, security-cam night aesthetic, "
    "extreme low light blue-green ambient, film grain, hyper-realistic"
)
NEG = (
    "cartoon, anime, illustration, text overlay, watermark, logo, bright daylight, "
    "sunny, cheerful, smiling faces looking at camera, gore puddles, deformed hands, "
    "extra fingers, blurry, lowres, overexposed flash washout, comic book"
)

BEATS = [
    {
        "id": "b0_spike",
        "sec": 3.0,
        "caption": "My sleep app recorded an audio spike at 3:17 AM...",
        "still": (
            f"{ROOM}, close view of smartphone screen showing minimal dark sleep-tracking app UI, "
            "audio waveform with sudden tall spike, timestamp 3:17 AM, label Unidentified Sound, "
            "glowing cyan UI on black phone, thumbs holding phone, tense mood"
        ),
        "visual": (
            f"{ROOM}, smartphone sleep app on screen with 3:17 AM unidentified sound spike waveform, "
            "cyan UI glow lighting the dark room faintly"
        ),
        "motion": (
            "subtle handheld shake, thumb hovering near screen, waveform pulse once, "
            "breathing camera sway, no cuts"
        ),
    },
    {
        "id": "b1_play",
        "sec": 3.0,
        "caption": "Listen closely to the audio playback...",
        "still": (
            f"{ROOM}, extreme close-up of finger tapping the play button on the sleep-tracker "
            "recording, phone speaker grille visible, dark bedroom bokeh behind"
        ),
        "visual": (
            f"{ROOM}, finger pressing play on sleep recording, phone speaker active, "
            "dark bedroom, found-footage POV"
        ),
        "motion": (
            "thumb taps play button, tiny screen reaction, slight zoom in toward phone, "
            "nervous micro-shake"
        ),
    },
    {
        "id": "b2_whisper",
        "sec": 3.0,
        "caption": "Wait... he's listening to us right now.",
        "still": (
            f"{ROOM}, POV looking past glowing phone toward dark foot of bed, "
            "listener frozen, phone screen still showing waveform, dread atmosphere, "
            "cold cyan rim light"
        ),
        "visual": (
            f"{ROOM}, frozen listener POV holding phone, dark empty foot of bed ahead, "
            "phone glow, extreme tension"
        ),
        "motion": (
            "camera freezes almost still, tiny tremor of fear, phone glow flickers once, "
            "shadow suggestion at bed foot, no face visible of intruder yet"
        ),
    },
    {
        "id": "b3_flash",
        "sec": 3.0,
        "caption": "WHY DID MY PHONE FLASHLIGHT TURN ON?!",
        "still": (
            f"{ROOM}, smartphone rear flashlight suddenly blazing on, harsh white beam cutting "
            "through darkness toward foot of bed, phone screen glitch digital artifacts, "
            "terrified POV freeze"
        ),
        "visual": (
            f"{ROOM}, phone flashlight auto-on blinding beam, screen glitch, "
            "harsh contrast night horror"
        ),
        "motion": (
            "sudden flash pop, digital glitch flicker on phone edges, camera jolts once then freezes, "
            "beam sweeps slightly toward mattress foot"
        ),
    },
    {
        "id": "b4_hands",
        "sec": 3.0,
        "caption": "LOOK AT THE FOOT OF THE BED.",
        "still": (
            f"{ROOM}, phone flashlight illuminating two elongated gray bone-thin unnatural hands "
            "slowly reaching up over the foot of the bed gripping the mattress edge, "
            "hyper-realistic horror, high tension shadows, no full creature body yet"
        ),
        "visual": (
            f"{ROOM}, flashlight beam on two bone-thin gray hands gripping mattress at foot of bed, "
            "jump-scare framing, hyper-realistic"
        ),
        "motion": (
            "hands slowly rise and grip mattress harder, fingers curl, mattress sinks slightly, "
            "camera shakes in terror, jump-scare intensity"
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

    try:
        urllib.request.urlopen(f"{config.COMFYUI_URL}/system_stats", timeout=3)
        return
    except Exception:
        pass
    print("COMFY_START", flush=True)
    if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
        raise RuntimeError("ComfyUI failed to start")


def flux_still(prompt: str, prefix: str, seed: int) -> Path:
    dest = WORK / "stills" / f"{prefix}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 40_000:
        print(f"STILL_REUSE {dest.name}", flush=True)
        return dest
    _ensure_comfy()
    wf = load_workflow(config.resolve_workflow_flux())
    job = apply_scene_to_workflow(
        wf,
        visual_prompt=prompt,
        motion_prompt="",
        filename_prefix=f"sleep317_{prefix}",
        width=STILL_W,
        height=STILL_H,
        node_map=config.NODE_MAP_FLUX,
        include_motion_in_prompt=False,
        cinematic_suffix=(
            "cinematic found-footage horror, photorealistic, 4k detail, "
            "dark atmospheric grain, high tension shadows"
        ),
        negative_prompt=NEG,
        seed=seed,
    )
    print(f"FLUX {prefix}", flush=True)
    _, paths = run_workflow(job, client_id=new_client_id(), timeout_s=2400)
    best = pick_best_output(paths, f"sleep317_{prefix}", allow_stale_disk=True)
    if best is None:
        from comfy_runner import latest_files_with_prefix

        imgs = [
            p
            for p in latest_files_with_prefix(f"sleep317_{prefix}")
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ]
        best = imgs[0] if imgs else None
    if not best:
        raise RuntimeError(f"Still missing for {prefix}")
    shutil.copy2(best, dest)
    print(f"STILL_OK {dest}", flush=True)
    time.sleep(COOLDOWN)
    return dest


def wan_clip(still: Path, beat: dict, seed: int) -> Path:
    dest = WORK / "clips" / f"{beat['id']}.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 60_000 and _ffprobe_dur(dest) >= beat["sec"] - 0.35:
        print(f"WAN_REUSE {dest.name}", flush=True)
        return dest
    chunk = WORK / "chunks" / f"{beat['id']}_l{WAN_LEN}.mp4"
    chunk.parent.mkdir(parents=True, exist_ok=True)
    if not (chunk.exists() and chunk.stat().st_size > 40_000):
        print(f"WAN {beat['id']} {WW}x{WH} len={WAN_LEN} steps={WAN_STEPS}", flush=True)
        two_pass_wan(
            still,
            visual=beat["visual"],
            motion=beat["motion"],
            prefix=f"sleep317_{beat['id']}",
            seed=seed,
            neg=NEG,
            out_mp4=chunk,
            ww=WW,
            wh=WH,
            length=WAN_LEN,
            steps=WAN_STEPS,
            cfg=WAN_CFG,
        )
        time.sleep(COOLDOWN)
    # Trim/pad to exact beat length @24fps for clean stitch
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(chunk),
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
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
    print(f"WAN_OK {dest} ({_ffprobe_dur(dest):.2f}s)", flush=True)
    return dest


def stitch_hard(clips: list[Path], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    lst = WORK / "concat.txt"
    lines = []
    for c in clips:
        lines.append(f"file '{c.resolve().as_posix()}'")
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
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


def upscale_hq(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={OUT_W}:{OUT_H}:flags=lanczos,"
        f"eq=contrast=1.08:brightness=-0.02:saturation=0.92:gamma=0.95,"
        f"unsharp=3:3:0.55:3:3:0.0,"
        f"noise=alls=6:allf=t"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-b:v",
            BITRATE,
            "-pix_fmt",
            "yuv420p",
            "-r",
            "24",
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
    stereo = np.column_stack([pcm, pcm]).astype(np.float32)
    interleaved = (stereo.reshape(-1) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(interleaved.tobytes())
    return path


def _edge_whisper(text: str, dest: Path) -> Path | None:
    try:
        import asyncio

        import edge_tts
    except ImportError:
        log.warning("edge-tts missing")
        return None

    mp3 = dest.with_suffix(".mp3")

    async def _run() -> None:
        # Soft low whisper-ish neural voice
        communicate = edge_tts.Communicate(text, "en-US-JennyNeural", rate="-12%", pitch="-10Hz")
        await communicate.save(str(mp3))

    try:
        asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        log.warning("edge-tts failed: %s", exc)
        return None
    # Convert + darken
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(mp3),
            "-af",
            "asetrate=44100*0.88,aresample=44100,volume=1.35,highpass=f=200,lowpass=f=3200",
            str(dest),
        ],
        check=False,
        capture_output=True,
    )
    return dest if dest.exists() else None


def build_horror_bed(dur: float, work: Path) -> Path:
    """Procedural bed matching audio_script beats + optional Edge-TTS whispers."""
    sr = 44100
    n = int(dur * sr)
    t = np.arange(n, dtype=np.float64) / sr
    audio = np.zeros(n, dtype=np.float64)

    # 0-3: sub-bass + room
    room = 0.04 * np.sin(2 * math.pi * 38 * t) + 0.015 * np.random.randn(n)
    audio += room * np.clip(1.0 - (t - 3.0) / 0.5, 0, 1)  # keep under later

    # continuous quiet room
    audio += 0.012 * np.random.randn(n)

    # 3-6: sheets + breathing (phone playback)
    for i in range(n):
        tt = t[i]
        if 3.0 <= tt < 6.0:
            audio[i] += 0.05 * math.sin(2 * math.pi * 1.1 * tt) * math.sin(2 * math.pi * 180 * tt)
            audio[i] += 0.03 * abs(math.sin(2 * math.pi * 0.35 * tt)) * np.random.randn()

    # 6-9: vacuum dip then whispers later mixed
    for i in range(n):
        tt = t[i]
        if 6.0 <= tt < 6.35:
            audio[i] *= 0.15  # sudden vacuum
        if 8.55 <= tt < 9.0:
            audio[i] *= 0.2

    # 9-12: electronic whine + click
    for i in range(n):
        tt = t[i]
        if 9.0 <= tt < 12.0:
            audio[i] += 0.04 * math.sin(2 * math.pi * 2400 * tt) * (0.5 + 0.5 * math.sin(2 * math.pi * 3 * tt))
        if 9.85 <= tt < 10.05:
            audio[i] += 0.55 * math.exp(-((tt - 9.9) ** 2) / 0.0004) * np.random.randn()

    # 12-15: creak + bone crack + sting
    for i in range(n):
        tt = t[i]
        if 12.0 <= tt < 14.2:
            audio[i] += 0.08 * math.sin(2 * math.pi * 90 * tt) * math.sin(2 * math.pi * 2.2 * tt)
            audio[i] += 0.05 * np.random.randn() * (1 if int(tt * 8) % 3 == 0 else 0.2)
        if 14.15 <= tt < 14.55:
            # jump-scare sting
            audio[i] += 0.7 * math.sin(2 * math.pi * 55 * tt) * math.exp(-((tt - 14.25) ** 2) / 0.01)
            audio[i] += 0.45 * np.random.randn() * math.exp(-((tt - 14.25) ** 2) / 0.008)

    bed = work / "horror_bed.wav"
    _write_wav(bed, audio, sr)

    # Layer Edge-TTS whispers at 6.4s and 7.6s
    w1 = _edge_whisper("He's breathing too loud...", work / "w1.wav")
    w2 = _edge_whisper("Wait... he's listening to us right now.", work / "w2.wav")
    inputs = ["-i", str(bed)]
    filters = ["[0:a]volume=1.0[a0]"]
    mix_in = ["[a0]"]
    idx = 1
    if w1 and w1.exists():
        inputs += ["-i", str(w1)]
        filters.append(f"[{idx}:a]volume=1.6,adelay=6400|6400[w1]")
        mix_in.append("[w1]")
        idx += 1
    if w2 and w2.exists():
        inputs += ["-i", str(w2)]
        filters.append(f"[{idx}:a]volume=1.75,adelay=7600|7600[w2]")
        mix_in.append("[w2]")
        idx += 1
    mixed = work / "horror_mix.wav"
    if len(mix_in) == 1:
        shutil.copy2(bed, mixed)
        return mixed
    fc = ";".join(filters) + ";" + "".join(mix_in) + f"amix=inputs={len(mix_in)}:duration=first:dropout_transition=0[aout]"
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", fc, "-map", "[aout]", str(mixed)]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError:
        shutil.copy2(bed, mixed)
    return mixed


def burn_captions(video: Path, audio: Path, dest: Path) -> Path:
    from moviepy.editor import AudioFileClip, CompositeVideoClip, VideoFileClip

    # Neon cyan captions, upper third
    old_color = getattr(config, "CAPTION_COLOR", "white")
    old_stroke = getattr(config, "CAPTION_STROKE", "black")
    old_fs = getattr(config, "CAPTION_FONTSIZE", 48)
    old_box = getattr(config, "CAPTION_BOX_W", 960)
    config.CAPTION_COLOR = "#00F6FF"
    config.CAPTION_STROKE = "black"
    config.CAPTION_STROKE_WIDTH = 4
    config.CAPTION_FONTSIZE = 52
    config.CAPTION_BOX_W = 980

    from editor import _caption_overlay_clip

    raw = VideoFileClip(str(video))
    overlays = []
    t0 = 0.0
    for beat in BEATS:
        dur = float(beat["sec"])
        cap = _caption_overlay_clip(
            beat["caption"],
            OUT_W,
            OUT_H,
            dur,
            fade_out=0.12,
            position="top",
            y_rel=0.14,
        ).set_start(t0)
        overlays.append(cap)
        t0 += dur
    comp = CompositeVideoClip([raw, *overlays], size=(OUT_W, OUT_H))
    a = AudioFileClip(str(audio)).subclip(0, min(comp.duration, _ffprobe_dur(audio)))
    comp = comp.set_audio(a)
    comp.write_videofile(
        str(dest),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        bitrate=BITRATE,
        preset="slow",
        ffmpeg_params=["-pix_fmt", "yuv420p"],
        logger=None,
    )
    comp.close()
    raw.close()
    a.close()
    config.CAPTION_COLOR = old_color
    config.CAPTION_STROKE = old_stroke
    config.CAPTION_FONTSIZE = old_fs
    config.CAPTION_BOX_W = old_box
    return dest


def write_caption_file() -> None:
    text = (
        "Delete your sleep tracking apps immediately... 📱🛌💀\n\n"
        "If your phone records voices in your room at 3 AM, DO NOT press play while you're still in bed.\n\n"
        "Tag someone who uses a sleep app every night! 👇\n\n"
        "#HorrorReels #FoundFootage #SleepHorror #JumpScare #CreepyPasta "
        "#HorrorTok #TechHorror #NightmareFuel #SpookySeason\n"
    )
    CAPTION_OUT.write_text(text, encoding="utf-8")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    WORK.mkdir(parents=True, exist_ok=True)
    (ROOT / "final_outputs").mkdir(parents=True, exist_ok=True)
    config.refresh_workflow_paths()
    print("FLUX", config.resolve_workflow_flux().name, config.gguf_flux_ready(), flush=True)
    print("WAN", config.resolve_workflow_wan().name, config.gguf_wan_ready(), flush=True)
    print(f"FORMAT 9:16 still {STILL_W}x{STILL_H} -> Wan {WW}x{WH} -> master {OUT_W}x{OUT_H}", flush=True)
    print(f"BEATS {len(BEATS)} x ~3s | steps={WAN_STEPS}", flush=True)

    if not config.gguf_flux_ready() or not config.gguf_wan_ready():
        raise RuntimeError("GGUF Flux/Wan not ready — enable USE_GGUF_5070_PROFILE and models")

    stills: list[Path] = []
    for i, beat in enumerate(BEATS):
        stills.append(flux_still(beat["still"], beat["id"], SEED0 + i * 97))

    clips: list[Path] = []
    for i, beat in enumerate(BEATS):
        print(f"\n=== BEAT {i+1}/{len(BEATS)} {beat['id']} ===", flush=True)
        clips.append(wan_clip(stills[i], beat, SEED0 + 1000 + i * 41))

    rough = WORK / "rough_480.mp4"
    stitch_hard(clips, rough)
    print(f"STITCH_OK {rough} ({_ffprobe_dur(rough):.2f}s)", flush=True)

    hq = WORK / "hq_1080.mp4"
    upscale_hq(rough, hq)
    print(f"UPSCALE_OK {hq}", flush=True)

    bed = build_horror_bed(_ffprobe_dur(hq), WORK / "audio")
    print(f"AUDIO_OK {bed}", flush=True)

    burn_captions(hq, bed, OUT)
    write_caption_file()
    print(f"FINAL {OUT} ({_ffprobe_dur(OUT):.2f}s) bytes={OUT.stat().st_size}", flush=True)
    print(f"CAPTION_FILE {CAPTION_OUT}", flush=True)
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
