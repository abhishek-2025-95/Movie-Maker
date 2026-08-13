"""Quality evidence for a DirectorX master: ffprobe + frames + still QC + report.

Usage:
  python -u scripts/analyze_video_quality.py
  python -u scripts/analyze_video_quality.py final_outputs\\US_Brooklyn_Stoop_Almost_10s.mp4
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from still_qc import is_unusable_still

DEFAULT_VIDEO = ROOT / "final_outputs" / "US_Brooklyn_Stoop_Almost_10s_v2.mp4"
DEFAULT_WORK = ROOT / "temp" / "us_stoop_almost_10s_v2"
DEFAULT_REPORT = DEFAULT_WORK / "quality_run_report.json"


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _ffprobe() -> str:
    found = shutil.which("ffprobe")
    if found:
        return found
    ffmpeg = Path(_ffmpeg())
    sibling = ffmpeg.parent / ("ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe")
    if sibling.is_file():
        return str(sibling)
    return "ffprobe"


def find_video(preferred: Path) -> Path | None:
    if preferred.is_file():
        return preferred
    out_dir = ROOT / "final_outputs"
    if not out_dir.is_dir():
        return None
    mp4s = [p for p in out_dir.glob("*.mp4") if p.is_file() and p.stat().st_size > 10_000]
    if not mp4s:
        return None
    return max(mp4s, key=lambda p: p.stat().st_mtime)


def ffprobe_json(path: Path) -> dict:
    raw = subprocess.check_output(
        [
            _ffprobe(),
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    return json.loads(raw)


def extract_frames(video: Path, dest: Path, stamps: list[float]) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for i, t in enumerate(stamps):
        png = dest / f"qc_{i:02d}_{t:.2f}s.png"
        subprocess.run(
            [
                _ffmpeg(),
                "-y",
                "-ss",
                f"{max(0.0, t):.3f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                str(png),
            ],
            check=True,
            capture_output=True,
        )
        out.append(png)
    return out


def analyze(video: Path, work: Path | None = None) -> dict:
    if not video.is_file():
        raise FileNotFoundError(f"Video not found: {video}")
    meta = ffprobe_json(video)
    fmt = meta.get("format") or {}
    streams = meta.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), {})
    dur = float(fmt.get("duration") or v.get("duration") or 0)
    width = int(v.get("width") or 0)
    height = int(v.get("height") or 0)
    fps_txt = str(v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1")
    try:
        n, d = fps_txt.split("/")
        fps = float(n) / float(d) if float(d) else 0.0
    except ValueError:
        fps = float(fps_txt or 0)
    bitrate = int(fmt.get("bit_rate") or 0)
    size = video.stat().st_size

    stamps = [0.15, dur * 0.25, dur * 0.5, dur * 0.75, max(0.05, dur - 0.25)]
    frame_dir = (work or video.parent) / "qc_frames"
    frames = extract_frames(video, frame_dir, stamps)
    frame_qc = []
    for p in frames:
        bad = is_unusable_still(p)
        frame_qc.append({"file": str(p), "unusable_still": bad, "bytes": p.stat().st_size})

    report_path = (work or DEFAULT_WORK) / "quality_run_report.json"
    report = None
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))

    checks = {
        "exists": True,
        "duration_10s": 9.4 <= dur <= 10.6,
        "master_1080": (width, height) in {(1920, 1080), (1080, 1920)},
        "fps_24ish": 23.0 <= fps <= 25.0,
        "has_audio": bool(a),
        "audio_stereo": int(a.get("channels") or 0) >= 2,
        "bitrate_10mbps_plus": bitrate >= 8_000_000 or size >= 1_000_000,
        "frames_usable": all(not x["unusable_still"] for x in frame_qc),
        "no_freeze_pad_flag": not bool((report or {}).get("freeze_pad", False)),
        "two_pass": (report or {}).get("wan_path") == "two_pass_moe",
        "wan_steps_14": int((report or {}).get("wan_steps") or 0) >= 14,
    }
    return {
        "video": str(video),
        "duration_s": round(dur, 3),
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "bitrate": bitrate,
        "bytes": size,
        "video_codec": v.get("codec_name"),
        "audio_codec": a.get("codec_name"),
        "audio_channels": a.get("channels"),
        "frames": frame_qc,
        "report": report,
        "checks": checks,
        "pass": all(checks.values()),
    }


def main() -> int:
    print(f"ROOT={ROOT}", flush=True)
    print(f"ffmpeg={_ffmpeg()}", flush=True)
    print(f"ffprobe={_ffprobe()}", flush=True)
    video = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_VIDEO
    if not video.is_absolute():
        video = ROOT / video
    found = find_video(video)
    if found is None:
        extras = list((ROOT / "final_outputs").glob("*")) if (ROOT / "final_outputs").is_dir() else []
        print(f"FATAL Video not found: {video}", flush=True)
        print(f"final_outputs listing: {[p.name for p in extras]}", flush=True)
        print("Render first, then analyse the mp4.", flush=True)
        return 1
    if found != video:
        print(f"Using newest mp4 (requested missing): {found}", flush=True)
    video = found
    print(f"VIDEO={video} bytes={video.stat().st_size}", flush=True)
    work = DEFAULT_WORK if "stoop" in video.name.lower() or "Brooklyn" in video.name else video.parent
    try:
        result = analyze(video, work)
    except FileNotFoundError as exc:
        print(f"FATAL {exc}", flush=True)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL analyze failed: {exc}", flush=True)
        traceback.print_exc()
        return 1
    print(json.dumps({k: v for k, v in result.items() if k != "report"}, indent=2), flush=True)
    if result.get("report"):
        print("\n=== quality_run_report.json ===", flush=True)
        print(json.dumps(result["report"], indent=2), flush=True)
    print("\n=== EYEBALL (open qc_frames) ===", flush=True)
    print("- Same two faces in first and last frame? (identity lock)", flush=True)
    print("- Melted face / extra limbs / kiss collapse?", flush=True)
    print("- Last frame frozen copy of an earlier frame? (freeze-pad)", flush=True)
    print("- Soft 480 look vs sharp 1080 faces?", flush=True)
    print("- Hands almost-touch, not a morph smear?", flush=True)
    print("PASS" if result["pass"] else "FAIL", result["checks"], flush=True)
    print(f"FRAMES_DIR={(work or video.parent) / 'qc_frames'}", flush=True)
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
