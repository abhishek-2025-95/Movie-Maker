"""Romance Wan Premium v5 — near-A long two-pass MoE, no freeze pads.

System ceiling (smoked): length=193 (~12.1s) @ 480x832 two-pass.
Beats ≤12.1s → single shot. Longer beats → continuation chunk from last frame
+ 1.0s xfade stitch so motion covers full beat duration.
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
from director import TopicJob, generate_screenplay
from editor import assemble_video
from pipeline import _scene_visual_for_flux
from utils import restart_comfyui
from voice import synthesize
from wan_two_pass_moe import two_pass_wan

log = logging.getLogger("romance_wan_v5")

WORK = ROOT / "temp" / "romance_wan_premium_v5"
OUT = ROOT / "final_outputs" / "Mumbai_Rain_Metro_Love_Story_Wan_Premium_v5.mp4"
TOPIC = "Mumbai Rain Metro Love Story Wan Premium v5 — near-A long MoE smooth"

WAN_FPS = 16.0
MAX_LEN = 121  # 193 flaky after disk pressure; 121 smoked OK + more headroom on 12GB/low free disk
MIN_LEN = 81
OVERLAP_SEC = 1.0
WW, WH = 480, 832
WAN_STEPS = 10  # proven
WAN_CFG = 4.5
SEED_BASE = 27072740
CHUNK_RETRIES = 2
LENGTH_FALLBACK = [121, 81]
COOLDOWN_SEC = 15


def _ceil_4n1(frames: int) -> int:
    frames = max(17, int(frames))
    n = (frames - 1 + 3) // 4
    return 4 * n + 1


def plan_chunks(target_sec: float) -> list[int]:
    """Wan lengths so xfade-stitched coverage >= target_sec."""
    lengths: list[int] = []
    covered = 0.0
    target = float(target_sec)
    while covered < target - 0.02:
        remain = target - covered
        gen_sec = remain if not lengths else remain + OVERLAP_SEC
        length = _ceil_4n1(int(math.ceil(gen_sec * WAN_FPS)))
        length = max(MIN_LEN, min(MAX_LEN, length))
        if gen_sec >= (MAX_LEN / WAN_FPS) * 0.92:
            length = MAX_LEN
        lengths.append(length)
        dur = length / WAN_FPS
        covered = dur if len(lengths) == 1 else covered + (dur - OVERLAP_SEC)
        if len(lengths) > 8:
            raise RuntimeError(f"chunk plan exploded for target={target}")
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
    """Chain xfade across clips; trim not applied here."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if len(clips) == 1:
        shutil.copy2(clips[0], dest)
        return dest
    # Build filter for N clips
    # [0][1]xfade=...:offset=d0-ov[v01]; [v01][2]xfade=...[v02]; ...
    durs = [_ffprobe_dur(c) for c in clips]
    args = ["ffmpeg", "-y"]
    for c in clips:
        args.extend(["-i", str(c)])
    filters = []
    # cumulative timeline offset for next xfade
    # offset_k = sum(dur_i for i<=k) - (k+1)*overlap  ... for sequential
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
    fc = ";".join(filters)
    args.extend(
        [
            "-filter_complex",
            fc,
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
    if not dest.exists() or dest.stat().st_size < 10_000:
        raise RuntimeError(f"xfade produced empty file: {dest}")
    log.info("Stitched %s clips → %s (%.2fs)", len(clips), dest.name, _ffprobe_dur(dest))
    return dest


def _ensure_comfy() -> None:
    import urllib.request

    try:
        urllib.request.urlopen(f"http://{config.COMFYUI_HOST}/system_stats", timeout=3)
        log.info("ComfyUI already up")
        return
    except Exception:
        pass
    if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
        raise RuntimeError("Failed to start ComfyUI")


def render_beat_smooth(
    *,
    still: Path,
    visual: str,
    motion: str,
    prefix: str,
    seed: int,
    neg: str,
    target_sec: float,
) -> Path:
    dest = WORK / f"{prefix}_wan.mp4"
    if dest.exists() and dest.stat().st_size > 100_000:
        dur = _ffprobe_dur(dest)
        if dur >= target_sec - 0.15:
            log.info("Reuse beat clip %s (%.2fs >= %.2fs)", dest.name, dur, target_sec)
            return dest

    lengths = plan_chunks(target_sec)
    log.info(
        "Beat %s plan target=%.2fs lengths=%s (~%s)",
        prefix,
        target_sec,
        lengths,
        [round(L / WAN_FPS, 2) for L in lengths],
    )

    chunk_paths: list[Path] = []
    plate = still
    for ci, length in enumerate(lengths):
        chunk_out = WORK / f"{prefix}_c{ci:02d}_len{length}.mp4"
        if chunk_out.exists() and chunk_out.stat().st_size > 100_000:
            log.info("Reuse chunk %s", chunk_out.name)
            chunk_paths.append(chunk_out)
            if ci < len(lengths) - 1:
                next_plate = WORK / f"{prefix}_c{ci:02d}_last.png"
                _extract_last_frame(chunk_out, next_plate)
                plate = next_plate
            continue

        # Prefer planned length; fall back if Comfy dies (VRAM cliff).
        try_lens = [length] + [L for L in LENGTH_FALLBACK if L < length]
        last_err: Exception | None = None
        made: Path | None = None
        used_len = length
        for try_len in try_lens:
            for attempt in range(1, CHUNK_RETRIES + 1):
                try_out = WORK / f"{prefix}_c{ci:02d}_len{try_len}.mp4"
                log.info(
                    "Chunk %s try length=%s attempt=%s/%s",
                    prefix,
                    try_len,
                    attempt,
                    CHUNK_RETRIES,
                )
                try:
                    two_pass_wan(
                        plate,
                        visual=visual,
                        motion=motion,
                        prefix=f"{prefix}_c{ci:02d}_L{try_len}",
                        seed=seed + ci * 97 + attempt,
                        neg=neg,
                        out_mp4=try_out,
                        ww=WW,
                        wh=WH,
                        length=try_len,
                        steps=WAN_STEPS,
                        cfg=WAN_CFG,
                    )
                    (WORK / f"{prefix}_c{ci:02d}_meta.txt").write_text(
                        f"{WW}x{WH} length={try_len} steps={WAN_STEPS} cfg={WAN_CFG} "
                        f"two_pass=1 seed={seed + ci * 97 + attempt} plate={plate.name}\n",
                        encoding="utf-8",
                    )
                    made = try_out
                    used_len = try_len
                    last_err = None
                    break
                except Exception as exc:  # noqa: BLE001
                    last_err = exc
                    log.warning(
                        "Chunk fail %s len=%s attempt=%s: %s",
                        prefix,
                        try_len,
                        attempt,
                        exc,
                    )
                    # Cool down — avoid restart thrash (two_pass already restarts Comfy)
                    time.sleep(COOLDOWN_SEC)
            if made is not None:
                break
        if made is None:
            raise RuntimeError(f"All chunk attempts failed for {prefix} c{ci}: {last_err}")
        # Normalize name for stitch list
        if made != chunk_out and used_len == length:
            shutil.copy2(made, chunk_out)
            made = chunk_out
        elif used_len != length:
            chunk_out = made
            log.warning("%s c%s fell back to length=%s", prefix, ci, used_len)
        chunk_paths.append(chunk_out)
        if ci < len(lengths) - 1:
            next_plate = WORK / f"{prefix}_c{ci:02d}_last.png"
            _extract_last_frame(chunk_out, next_plate)
            plate = next_plate
        time.sleep(COOLDOWN_SEC)

    raw = WORK / f"{prefix}_wan_raw.mp4"
    if len(chunk_paths) == 1:
        shutil.copy2(chunk_paths[0], raw)
    else:
        _xfade_stitch(chunk_paths, raw, OVERLAP_SEC)

    # Cover target with ping-pong if tiny shortfall — never freeze-pad a still frame.
    dur = _ffprobe_dur(raw)
    if dur + 0.05 >= target_sec:
        # Trim to exact beat length for clean assemble
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(raw),
                "-t",
                f"{target_sec:.4f}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "medium",
                "-crf",
                "17",
                "-an",
                str(dest),
            ],
            check=True,
            capture_output=True,
        )
    else:
        # Ping-pong: forward + reverse to fill without a frozen hold
        need = target_sec
        log.warning(
            "%s dur=%.2fs < target=%.2fs — ping-pong fill (no freeze)",
            prefix,
            dur,
            target_sec,
        )
        rev = WORK / f"{prefix}_rev.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(raw),
                "-vf",
                "reverse",
                "-an",
                str(rev),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(raw),
                "-i",
                str(rev),
                "-filter_complex",
                f"[0][1]concat=n=2:v=1:a=0,trim=0:{need:.4f},setpts=PTS-STARTPTS",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "medium",
                "-crf",
                "17",
                "-an",
                str(dest),
            ],
            check=True,
            capture_output=True,
        )
    log.info("Beat ready %s dur=%.2fs target=%.2fs", dest.name, _ffprobe_dur(dest), target_sec)
    return dest


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    WORK.mkdir(parents=True, exist_ok=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        import psutil

        me = psutil.Process()
        twins = []
        for p in psutil.process_iter(["pid", "cmdline"]):
            if p.info.get("pid") in {me.pid, me.ppid()}:
                continue
            cmd = " ".join(p.info.get("cmdline") or [])
            if "render_romance_wan_premium_v5.py" in cmd or "render_romance_wan_premium.py" in cmd:
                twins.append(p.info.get("pid"))
        if twins:
            raise RuntimeError(f"Another romance Wan render running: {twins}")
    except ImportError:
        pass

    _ensure_comfy()
    job = TopicJob(topic=TOPIC, mode="character", style="live", ratio="9:16", lang="en")
    sp = generate_screenplay(job)
    assert len(sp.scenes) == 8
    beat_durs = [float(x) for x in (sp.raw.get("beat_durations") or [15.0] * 8)]
    neg = config.FLUX_NEGATIVE_PROMPT

    # Flux plates from v4/v3
    src_dirs = [
        ROOT / "temp" / "romance_wan_premium_v4",
        ROOT / "temp" / "romance_wan_premium_v3",
        ROOT / "temp" / "Mumbai_Rain_Metro_Love_Story_2-minute_8-",
    ]

    clip_paths: list[Path] = []
    narr_paths: list[Path] = []

    for idx, scene in enumerate(sp.scenes):
        prefix = f"dx_rom_v5_s{idx:02d}"
        still = WORK / f"{prefix}_still.png"
        if not still.exists():
            copied = False
            for d in src_dirs:
                for name in (
                    f"dx_rom_wan_s{idx:02d}_still.png",
                    f"dx_rom_v5_s{idx:02d}_still.png",
                    f"dx_Mumbai_Rain_Metro_Love_Story_2-minute_8-_s{idx:02d}_still.png",
                ):
                    src = d / name
                    if src.exists():
                        shutil.copy2(src, still)
                        log.info("Reuse still %s → beat %s", src, idx + 1)
                        copied = True
                        break
                if copied:
                    break
            if not copied:
                raise FileNotFoundError(f"Missing Flux still for beat {idx}")
        else:
            log.info("Reuse Flux still %s", still.name)

        # narration: prefer v4 copy
        vo = WORK / f"narration_{idx:02d}.wav"
        if not vo.exists():
            for d in src_dirs:
                src_vo = d / f"narration_{idx:02d}.wav"
                if src_vo.exists():
                    shutil.copy2(src_vo, vo)
                    break
            if not vo.exists():
                synthesize(scene.narration, lang=job.lang, out_path=vo)
        narr_paths.append(vo)

        visual = _scene_visual_for_flux(
            scene, idx=idx, total=8, screenplay=sp, topic=job.topic
        )
        wan_mp4 = render_beat_smooth(
            still=still,
            visual=visual,
            motion=scene.motion_prompt,
            prefix=prefix,
            seed=SEED_BASE + idx * 17 + 3,
            neg=neg,
            target_sec=beat_durs[idx],
        )
        clip_paths.append(wan_mp4)
        log.info("Beat %s/%s ready", idx + 1, 8)

    # Mark meta so assemble trims rather than invents freezes when clip >= beat
    meta = dict(sp.raw or {})
    meta["wan_premium_v5"] = True
    meta["forbid_freeze_pad"] = True

    transitions = [s.transition_to_next for s in sp.scenes]
    assemble_video(
        clip_paths,
        narr_paths,
        out_path=OUT,
        ratio="9:16",
        burn_captions=False,
        caption_lines=None,
        transitions=transitions,
        screenplay_meta=meta,
    )
    log.info("DONE %s (%.1f MB) beats=%s", OUT, OUT.stat().st_size / 1e6, beat_durs)
    print(f"DONE {OUT}")


if __name__ == "__main__":
    main()
