"""Victorian Forbidden Love — cinematic proof (~30–35s).

Flux GGUF stills → Wan 2.2 GGUF two-pass → xfade assemble.
Run via: scripts/run_victorian_forbidden_external.bat (external terminal only).
"""
from __future__ import annotations

import logging
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config
from comfy_runner import apply_scene_to_workflow, load_workflow, pick_best_output, run_workflow
from utils import new_client_id, restart_comfyui
from wan_two_pass_moe import two_pass_wan

log = logging.getLogger("victorian_forbidden")

WORK = ROOT / "temp" / "victorian_forbidden"
OUT = ROOT / "final_outputs" / "Victorian_Forbidden_Love_Proof.mp4"

WAN_FPS = 16.0
MAX_LEN = 81
MIN_LEN = 81
OVERLAP_SEC = 0.85
WW, WH = 480, 832
STILL_W, STILL_H = 768, 1344
WAN_STEPS = 10
WAN_CFG = 4.5
SEED_BASE = 18850705
COOLDOWN_SEC = 12

LADY = (
    "young Victorian English woman mid-20s, porcelain skin, dark chestnut hair in elegant "
    "updo with soft loose curls, emerald green silk evening gown with lace collar, delicate "
    "gold earrings, almond brown eyes, soft rose lips, distinctive face identity lock"
)
GENT = (
    "Victorian English gentleman early 30s, clean-shaven strong jaw, short dark brown hair, "
    "black formal coat, charcoal waistcoat with gold watch chain, white collar and tie, "
    "intense grey-blue eyes, distinctive face identity lock"
)
LOCK = (
    f"same two people only: ({LADY}) and ({GENT}), photorealistic 1885 England period film, "
    "candlelit parlor, warm tungsten key, cool blue window rim light, shallow depth of field, "
    "35mm film still, high detail faces, no modern objects"
)

NEG = (
    config.FLUX_NEGATIVE_PROMPT
    + ", modern clothing, smartphone, neon, cartoon, anime, text, watermark, "
    "extra people, crowd, looking at camera, smile at viewer"
)

BEATS = [
    {
        "id": "b0_hold",
        "sec": 8.5,
        "flux": (
            f"{LOCK}, tight medium two-shot, faces inches apart, eyes locked with forbidden "
            "desire, candle flames soft bokeh, heavy velvet curtains, almost breathless"
        ),
        "motion": "soft blinks subtle breath micro lean-in eye flicker candlelight shimmer",
    },
    {
        "id": "b1_almost",
        "sec": 8.5,
        "flux": (
            f"{LOCK}, closer framing, his hand hovering near her waist, her fingers almost "
            "touching his lapel, lips parted close but not kissing, heat and restraint, "
            "intimate dangerous proximity"
        ),
        "motion": "fingers tremble slight lean closer shallow breath candle flicker",
    },
    {
        "id": "b2_threat",
        "sec": 8.0,
        "flux": (
            f"{LOCK}, same parlor, her eyes dart toward closed oak door in soft background, "
            "his head half-turns listening, bodies still pressed close, fear of being discovered"
        ),
        "motion": "eyes flick to door micro flinch head half-turn freeze tension",
    },
    {
        "id": "b3_break",
        "sec": 8.0,
        "flux": (
            f"{LOCK}, they step a half pace apart composing themselves, lingering longing "
            "in the eyes, candle smoke curl, unresolved forbidden passion"
        ),
        "motion": "step back straighten posture lingering eye contact candle smoke drift",
    },
]


def _ceil_4n1(frames: int) -> int:
    frames = max(17, int(frames))
    n = (frames - 1 + 3) // 4
    return 4 * n + 1


def plan_chunks(target_sec: float) -> list[int]:
    lengths: list[int] = []
    covered = 0.0
    target = float(target_sec)
    while covered < target - 0.02:
        remain = target - covered
        gen_sec = remain if not lengths else remain + OVERLAP_SEC
        length = _ceil_4n1(int(math.ceil(gen_sec * WAN_FPS)))
        length = max(MIN_LEN, min(MAX_LEN, length))
        lengths.append(length)
        dur = length / WAN_FPS
        covered = dur if len(lengths) == 1 else covered + (dur - OVERLAP_SEC)
        if len(lengths) > 6:
            break
    return lengths


def _ffprobe_dur(path: Path) -> float:
    out = subprocess.check_output(
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
        text=True,
    ).strip()
    return float(out)


def _extract_last_frame(mp4: Path, png: Path) -> Path:
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


def _xfade_stitch(clips: list[Path], dest: Path, overlap: float = OVERLAP_SEC) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if len(clips) == 1:
        shutil.copy2(clips[0], dest)
        return dest
    durs = [_ffprobe_dur(c) for c in clips]
    args = ["ffmpeg", "-y"]
    for c in clips:
        args.extend(["-i", str(c)])
    filters = []
    prev = "[0:v]"
    timeline = durs[0]
    for i in range(1, len(clips)):
        offset = max(0.05, timeline - overlap)
        out_lab = f"[v{i}]" if i < len(clips) - 1 else "[vout]"
        filters.append(
            f"{prev}[{i}:v]xfade=transition=fade:duration={overlap:.3f}:offset={offset:.3f}{out_lab}"
        )
        prev = out_lab
        timeline = timeline + durs[i] - overlap
    args.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[vout]",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-crf",
            "17",
            "-r",
            "24",
            str(dest),
        ]
    )
    try:
        subprocess.run(args, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or b"").decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"xfade stitch failed: {err}") from exc
    return dest


def _ensure_comfy() -> None:
    import urllib.request

    try:
        urllib.request.urlopen(f"http://{config.COMFYUI_HOST}/system_stats", timeout=3)
        log.info("ComfyUI already up")
        return
    except Exception:
        pass
    if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 150))):
        raise RuntimeError("Failed to start ComfyUI")


def render_still(prompt: str, prefix: str, seed: int) -> Path:
    dest = WORK / "stills" / f"{prefix}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 50_000:
        log.info("Reuse still %s", dest.name)
        return dest
    config.refresh_workflow_paths()
    _ensure_comfy()
    wf = load_workflow(config.resolve_workflow_flux())
    job = apply_scene_to_workflow(
        wf,
        visual_prompt=prompt,
        motion_prompt="",
        filename_prefix=prefix,
        width=STILL_W,
        height=STILL_H,
        node_map=config.NODE_MAP_FLUX,
        include_motion_in_prompt=False,
        cinematic_suffix=config.STYLE_SUFFIX["live"],
        negative_prompt=NEG,
        seed=seed,
    )
    log.info("FLUX %s seed=%s", prefix, seed)
    _, paths = run_workflow(job, client_id=new_client_id(), timeout_s=2400)
    best = pick_best_output(paths, prefix, allow_stale_disk=True)
    if best is None:
        from comfy_runner import latest_files_with_prefix

        imgs = [
            p
            for p in latest_files_with_prefix(prefix)
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ]
        best = imgs[0] if imgs else None
    if not best or not best.exists():
        raise RuntimeError(f"Flux still missing for {prefix}")
    shutil.copy2(best, dest)
    return dest


def render_beat(still: Path, beat: dict, seed: int) -> Path:
    prefix = beat["id"]
    dest = WORK / "clips" / f"{prefix}_wan.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = float(beat["sec"])
    if dest.exists() and dest.stat().st_size > 80_000 and _ffprobe_dur(dest) >= target - 0.2:
        log.info("Reuse clip %s", dest.name)
        return dest

    lengths = plan_chunks(target)
    log.info("WAN %s lengths=%s target=%.1fs", prefix, lengths, target)
    chunks: list[Path] = []
    frame = still
    for i, length in enumerate(lengths):
        chunk = WORK / "chunks" / f"{prefix}_c{i}_l{length}.mp4"
        chunk.parent.mkdir(parents=True, exist_ok=True)
        if chunk.exists() and chunk.stat().st_size > 50_000:
            chunks.append(chunk)
            frame = _extract_last_frame(chunk, WORK / "chunks" / f"{prefix}_c{i}_last.png")
            continue
        two_pass_wan(
            frame,
            visual=beat["flux"],
            motion=beat["motion"],
            prefix=f"{prefix}_c{i}",
            seed=seed + i * 17,
            neg=NEG,
            out_mp4=chunk,
            ww=WW,
            wh=WH,
            length=length,
            steps=WAN_STEPS,
            cfg=WAN_CFG,
        )
        chunks.append(chunk)
        frame = _extract_last_frame(chunk, WORK / "chunks" / f"{prefix}_c{i}_last.png")
        time.sleep(COOLDOWN_SEC)
    return _xfade_stitch(chunks, dest, overlap=OVERLAP_SEC)


def _add_audio_bed(video: Path, out: Path) -> Path:
    """Soft bed: low sine pad + silence-safe AAC. No TTS."""
    out.parent.mkdir(parents=True, exist_ok=True)
    dur = _ffprobe_dur(video)
    # Generate quiet warm pad with ffmpeg sine (very low volume)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=110:sample_rate=44100:duration={dur:.3f}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=164.81:sample_rate=44100:duration={dur:.3f}",
        "-filter_complex",
        "[1:a]volume=0.04[a1];[2:a]volume=0.03[a2];[a1][a2]amix=inputs=2:duration=first[a]",
        "-map",
        "0:v",
        "-map",
        "[a]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(out),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return out
    except subprocess.CalledProcessError:
        shutil.copy2(video, out)
        return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    WORK.mkdir(parents=True, exist_ok=True)
    (ROOT / "final_outputs").mkdir(parents=True, exist_ok=True)
    config.refresh_workflow_paths()
    print("FLUX", config.resolve_workflow_flux().name, "ready", config.gguf_flux_ready())
    print("WAN", config.resolve_workflow_wan().name, "ready", config.gguf_wan_ready())
    if not config.gguf_wan_ready():
        raise RuntimeError("Wan GGUF not ready")

    _ensure_comfy()
    beat_clips: list[Path] = []
    for i, beat in enumerate(BEATS):
        print(f"\n=== BEAT {i+1}/{len(BEATS)} {beat['id']} ===", flush=True)
        still = render_still(beat["flux"], f"vic_{beat['id']}_still", SEED_BASE + i * 101)
        clip = render_beat(still, beat, SEED_BASE + 1000 + i * 33)
        beat_clips.append(clip)
        print(f"BEAT_OK {clip} ({_ffprobe_dur(clip):.2f}s)", flush=True)

    silent = WORK / "proof_silent.mp4"
    _xfade_stitch(beat_clips, silent, overlap=0.75)
    print(f"STITCH_OK {silent} ({_ffprobe_dur(silent):.2f}s)", flush=True)
    _add_audio_bed(silent, OUT)
    print(f"FINAL {OUT} ({_ffprobe_dur(OUT):.2f}s) size={OUT.stat().st_size}", flush=True)
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
