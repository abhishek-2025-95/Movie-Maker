from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_video_quality import analyze


def test_analyze_missing_video(tmp_path):
    try:
        analyze(tmp_path / "nope.mp4")
    except FileNotFoundError:
        return
    assert False, "expected FileNotFoundError"
