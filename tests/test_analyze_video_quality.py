from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_video_quality import analyze, find_video
import analyze_video_quality as aq


def test_analyze_missing_video(tmp_path):
    try:
        analyze(tmp_path / "nope.mp4")
    except FileNotFoundError:
        return
    assert False, "expected FileNotFoundError"


def test_find_video_picks_newest(tmp_path, monkeypatch):
    out = tmp_path / "final_outputs"
    out.mkdir()
    a = out / "old.mp4"
    b = out / "new.mp4"
    a.write_bytes(b"x" * 20_000)
    b.write_bytes(b"y" * 20_000)
    monkeypatch.setattr(aq, "ROOT", tmp_path)
    got = find_video(tmp_path / "missing.mp4")
    assert got == b
