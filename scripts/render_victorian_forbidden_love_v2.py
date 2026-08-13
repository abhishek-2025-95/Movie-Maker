"""Victorian Forbidden Love v2 — pro jump pass.

Locks ONE Flux hero plate (16:9). Every Wan beat starts from that plate
(or a crop/pan of it — same pixels/faces). Hard cut into threat beat.
Shorter romantic xfade. Real-ish audio bed (room + door + strings).

External only: scripts/run_victorian_forbidden_v2_external.bat
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

log = logging.getLogger("victorian_v2")

WORK = ROOT / "temp" / "victorian_forbidden_v2"
OUT = ROOT / "final_outputs" / "Victorian_Forbidden_Love_Proof_v2.mp4"

WAN_FPS = 16.0
MAX_LEN = 81
MIN_LEN = 81
ROMANCE_XFADE = 0.30  # short
WW, WH = 832, 480  # 16:9 movie
STILL_W, STILL_H = 1344, 768
WAN_STEPS = 10
WAN_CFG = 4.5
SEED_HERO = 18850705
COOLDOWN_SEC = 12

LADY = (
    "young Victorian English woman mid-20s, porcelain skin, dark chestnut hair in elegant "
    "updo with soft loose curls, emerald green silk evening gown with lace collar, delicate "
    "gold earrings, almond brown eyes, soft rose lips, SAME FACE every frame identity lock"
)
GENT = (
    "Victorian English gentleman early 30s, CLEAN-SHAVEN strong jaw no beard no mustache, "
    "short dark brown hair neat, black formal coat, charcoal waistcoat with gold watch chain, "
    "white wing collar black bow tie, intense grey-blue eyes, SAME FACE every frame identity lock"
)
LOCK = (
    f"exactly these two people only: ({LADY}) and ({GENT}), photorealistic 1885 England, "
    "candlelit parlor oak door visible in soft background, warm tungsten key, cool blue "
    "window rim light, shallow depth of field but faces sharp, 35mm film, no modern objects"
)

NEG = (
    config.FLUX_NEGATIVE_PROMPT
    + ", beard, mustache, stubble, modern clothing, smartphone, neon, cartoon, anime, "
    "text, watermark, extra people, crowd, looking at camera, smile at viewer, "
    "motion blur, ghosting, double exposure, melted face, identity morph"
)

HERO_PROMPT = (
    f"{LOCK}, cinematic 16:9 medium two-shot, faces inches apart in profile, eyes locked "
    "with forbidden desire, lips close but not kissing, candle bokeh left, tall night window "
    "right, heavy velvet curtains, oak parlor door faintly visible behind them, sharp faces"
)

# Motion-only beats; all Wan chunk-0 starts from hero plate (or crop of hero).
BEATS = [
    {
        "id": "b0_hold",
        "sec": 8.0,
        "plate": "hero",
        "cut_in": "xfade",
        "motion": (
            "soft blinks subtle breath micro lean-in eye flicker candlelight shimmer "
            "faces stay sharp identity locked"
        ),
        "visual": HERO_PROMPT + ", holding the almost-kiss tension",
    },
    {
        "id": "b1_almost",
        "sec": 8.0,
        "plate": "hero_tight",
        "cut_in": "xfade",
        "motion": (
            "her fingers tremble toward his lapel his hand near her waist slight lean closer "
            "shallow breath candle flicker faces sharp no morph"
        ),
        "visual": HERO_PROMPT + ", closer intimacy heat restraint",
    },
    {
        "id": "b2_threat",
        "sec": 7.5,
        "plate": "hero_door",
        "cut_in": "hard",  # hard cut into threat
        "motion": (
            "BOTH freeze then her eyes clearly dart RIGHT toward oak door his head half-turns "
            "listening alarm fear of discovery sharp faces no blur smear"
        ),
        "visual": (
            f"{LOCK}, same couple, her face turned slightly listening toward oak door in "
            "background, his head half turned to door, bodies still close, clear threat beat, "
            "faces sharp readable"
        ),
    },
    {
        "id": "b3_break",
        "sec": 7.5,
        "plate": "hero_apart",
        "cut_in": "hard",  # hard cut after threat
        "motion": (
            "they step a clear half pace APART shoulders square lingering eye contact "
            "compose posture candle smoke drift faces sharp identity locked"
        ),
        "visual": (
            f"{LOCK}, couple half step apart after almost being caught, lingering longing "
            "eyes, composed faces, parlor space between them, sharp focus on both faces"
        ),
    },
]


def _ceil_4n1(frames: int) -> int:
    frames = max(17, int(frames))
    n = (frames - 1 + 3) // 4
    return 4 * n + 1


def plan_chunks(target_sec: float) -> list[int]:
    lengths: list[int] = []
    covered = 0.0
    while covered < float(target_sec) - 0.02:
        remain = float(target_sec) - covered
        gen_sec = remain if not lengths else remain + 0.85
        length = max(MIN_LEN, min(MAX_LEN, _ceil_4n1(int(math.ceil(gen_sec * WAN_FPS)))))
        lengths.append(length)
        dur = length / WAN_FPS
        covered = dur if len(lengths) == 1 else covered + (dur - 0.85)
        if len(lengths) > 5:
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
        ["ffmpeg", "-y", "-sseof", "-0.08", "-i", str(mp4), "-frames:v", "1", str(png)],
        check=True,
        capture_output=True,
    )
    if not png.exists() or png.stat().st_size < 1000:
        raise RuntimeError(f"last-frame extract failed: {mp4}")
    return png


def _ensure_comfy() -> None:
    import urllib.request

    try:
        urllib.request.urlopen(f"http://{config.COMFYUI_HOST}/system_stats", timeout=3)
        return
    except Exception:
        pass
    if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 150))):
        raise RuntimeError("Failed to start ComfyUI")


def render_hero_still() -> Path:
    dest = WORK / "stills" / "hero_still.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 80_000:
        log.info("Reuse hero still %s", dest)
        return dest
    config.refresh_workflow_paths()
    _ensure_comfy()
    wf = load_workflow(config.resolve_workflow_flux())
    job = apply_scene_to_workflow(
        wf,
        visual_prompt=HERO_PROMPT,
        motion_prompt="",
        filename_prefix="vic_v2_hero_still",
        width=STILL_W,
        height=STILL_H,
        node_map=config.NODE_MAP_FLUX,
        include_motion_in_prompt=False,
        cinematic_suffix=config.STYLE_SUFFIX["live"],
        negative_prompt=NEG,
        seed=SEED_HERO,
    )
    print("FLUX_HERO", flush=True)
    _, paths = run_workflow(job, client_id=new_client_id(), timeout_s=2400)
    best = pick_best_output(paths, "vic_v2_hero_still", allow_stale_disk=True)
    if best is None:
        from comfy_runner import latest_files_with_prefix

        imgs = [
            p
            for p in latest_files_with_prefix("vic_v2_hero")
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ]
        best = imgs[0] if imgs else None
    if not best:
        raise RuntimeError("Hero still missing")
    shutil.copy2(best, dest)
    print(f"HERO_OK {dest}", flush=True)
    return dest


def make_plates(hero: Path) -> dict[str, Path]:
    """Same-pixel identity plates via crop/pan of hero (no new faces)."""
    from PIL import Image

    plates_dir = WORK / "plates"
    plates_dir.mkdir(parents=True, exist_ok=True)
    im = Image.open(hero).convert("RGB")
    w, h = im.size
    out: dict[str, Path] = {"hero": hero}

    def save_crop(name: str, box: tuple[int, int, int, int]) -> Path:
        p = plates_dir / f"{name}.png"
        if p.exists() and p.stat().st_size > 20_000:
            out[name] = p
            return p
        crop = im.crop(box).resize((w, h), Image.LANCZOS)
        crop.save(p, format="PNG")
        out[name] = p
        return p

    # tight: center 85%
    m = int(min(w, h) * 0.08)
    save_crop("hero_tight", (m, m, w - m, h - m))
    # door bias: shift crop right to include more door/window side
    dx = int(w * 0.08)
    save_crop("hero_door", (dx, 0, w, h))
    # apart: slight zoom-out feel via letterbox pad then resize (same faces smaller in frame)
    pad = int(min(w, h) * 0.06)
    padded = Image.new("RGB", (w + 2 * pad, h + 2 * pad), (12, 8, 6))
    padded.paste(im, (pad, pad))
    apart = padded.resize((w, h), Image.LANCZOS)
    apart_path = plates_dir / "hero_apart.png"
    if not (apart_path.exists() and apart_path.stat().st_size > 20_000):
        apart.save(apart_path, format="PNG")
    out["hero_apart"] = apart_path
    return out


def render_beat(plate: Path, beat: dict, seed: int) -> Path:
    prefix = beat["id"]
    dest = WORK / "clips" / f"{prefix}_wan.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = float(beat["sec"])
    if dest.exists() and dest.stat().st_size > 80_000 and _ffprobe_dur(dest) >= target - 0.25:
        log.info("Reuse %s", dest.name)
        return dest

    lengths = plan_chunks(target)
    print(f"WAN {prefix} plate={plate.name} lengths={lengths}", flush=True)
    chunks: list[Path] = []
    frame = plate  # ALWAYS start beat from locked plate
    for i, length in enumerate(lengths):
        chunk = WORK / "chunks" / f"{prefix}_c{i}_l{length}.mp4"
        chunk.parent.mkdir(parents=True, exist_ok=True)
        if chunk.exists() and chunk.stat().st_size > 40_000:
            chunks.append(chunk)
            frame = _extract_last_frame(chunk, WORK / "chunks" / f"{prefix}_c{i}_last.png")
            continue
        two_pass_wan(
            frame,
            visual=beat["visual"],
            motion=beat["motion"],
            prefix=f"vic2_{prefix}_c{i}",
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
        # continuation within beat only
        frame = _extract_last_frame(chunk, WORK / "chunks" / f"{prefix}_c{i}_last.png")
        time.sleep(COOLDOWN_SEC)

    if len(chunks) == 1:
        shutil.copy2(chunks[0], dest)
        return dest
    return _xfade_chain(chunks, dest, overlap=0.85)


def _xfade_chain(clips: list[Path], dest: Path, overlap: float) -> Path:
    durs = [_ffprobe_dur(c) for c in clips]
    args = ["ffmpeg", "-y"]
    for c in clips:
        args += ["-i", str(c)]
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
        timeline += durs[i] - overlap
    args += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[vout]",
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "17",
        "-r",
        "24",
        str(dest),
    ]
    subprocess.run(args, check=True, capture_output=True)
    return dest


def assemble_beats(clips: list[Path], beats: list[dict], dest: Path) -> Path:
    """Hard cuts on threat; short xfade only between soft romance beats."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if len(clips) == 1:
        shutil.copy2(clips[0], dest)
        return dest

    # Build via sequential concat with selective xfade
    # Strategy: render pairs
    current = clips[0]
    temp_dir = WORK / "assemble"
    temp_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, len(clips)):
        cut = beats[i].get("cut_in", "hard")
        out = temp_dir / f"asm_{i}.mp4"
        if cut == "hard":
            # concat demuxer
            lst = temp_dir / f"list_{i}.txt"
            # re-encode current+next for concat safety
            a = temp_dir / f"a_{i}.mp4"
            b = temp_dir / f"b_{i}.mp4"
            for src, dst in ((current, a), (clips[i], b)):
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(src),
                        "-c:v",
                        "libx264",
                        "-pix_fmt",
                        "yuv420p",
                        "-r",
                        "24",
                        "-an",
                        str(dst),
                    ],
                    check=True,
                    capture_output=True,
                )
            lst.write_text(f"file '{a.as_posix()}'\nfile '{b.as_posix()}'\n", encoding="utf-8")
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
                    "-c",
                    "copy",
                    str(out),
                ],
                check=True,
                capture_output=True,
            )
        else:
            d0 = _ffprobe_dur(current)
            ov = ROMANCE_XFADE
            offset = max(0.05, d0 - ov)
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(current),
                    "-i",
                    str(clips[i]),
                    "-filter_complex",
                    f"[0:v][1:v]xfade=transition=fade:duration={ov:.3f}:offset={offset:.3f}[v]",
                    "-map",
                    "[v]",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-crf",
                    "17",
                    "-r",
                    "24",
                    str(out),
                ],
                check=True,
                capture_output=True,
            )
        current = out
    shutil.copy2(current, dest)
    return dest


def mix_audio(video: Path, out: Path) -> Path:
    """Room tone + door cue at threat + quiet strings."""
    dur = _ffprobe_dur(video)
    # Threat starts after beats 0+1 ≈ 8+8 - 0.3 xfade ≈ 15.7s
    door_at = 15.5
    door_dur = 0.55
    filter_complex = (
        f"anoisesrc=color=pink:amplitude=0.025:duration={dur:.3f}[room];"
        f"sine=frequency=196:duration={dur:.3f},volume=0.035[s1];"
        f"sine=frequency=246.94:duration={dur:.3f},volume=0.028[s2];"
        f"sine=frequency=293.66:duration={dur:.3f},volume=0.022[s3];"
        f"[s1][s2][s3]amix=inputs=3:duration=first,volume=0.7[strings];"
        # door: short noise burst delayed
        f"anoisesrc=color=brown:amplitude=0.45:duration={door_dur:.3f},"
        f"afade=t=in:st=0:d=0.02,afade=t=out:st={door_dur*0.35:.3f}:d={door_dur*0.65:.3f},"
        f"adelay={int(door_at*1000)}|{int(door_at*1000)}[door];"
        f"[room][strings][door]amix=inputs=3:duration=first:dropout_transition=0[a]"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v",
        "-map",
        "[a]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-shortest",
        str(out),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or b"").decode("utf-8", errors="replace")[-1500:]
        log.warning("audio mix failed, copying silent: %s", err)
        shutil.copy2(video, out)
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    WORK.mkdir(parents=True, exist_ok=True)
    (ROOT / "final_outputs").mkdir(parents=True, exist_ok=True)
    config.refresh_workflow_paths()
    print("FLUX", config.resolve_workflow_flux().name, config.gguf_flux_ready(), flush=True)
    print("WAN", config.resolve_workflow_wan().name, config.gguf_wan_ready(), flush=True)
    print("FORMAT 16:9", f"{STILL_W}x{STILL_H} -> Wan {WW}x{WH}", flush=True)

    hero = render_hero_still()
    plates = make_plates(hero)
    print("PLATES", {k: v.name for k, v in plates.items()}, flush=True)

    beat_clips: list[Path] = []
    for i, beat in enumerate(BEATS):
        print(f"\n=== BEAT {i+1}/{len(BEATS)} {beat['id']} cut={beat['cut_in']} ===", flush=True)
        plate = plates[beat["plate"]]
        clip = render_beat(plate, beat, SEED_HERO + 2000 + i * 41)
        beat_clips.append(clip)
        print(f"BEAT_OK {clip} ({_ffprobe_dur(clip):.2f}s)", flush=True)

    silent = WORK / "proof_silent.mp4"
    assemble_beats(beat_clips, BEATS, silent)
    print(f"STITCH_OK {silent} ({_ffprobe_dur(silent):.2f}s)", flush=True)
    mix_audio(silent, OUT)
    print(f"FINAL {OUT} ({_ffprobe_dur(OUT):.2f}s) bytes={OUT.stat().st_size}", flush=True)
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
