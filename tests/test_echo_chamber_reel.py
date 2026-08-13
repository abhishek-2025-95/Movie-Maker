"""Echo Chamber raw Reel lockdown."""
from director import TopicJob, generate_screenplay
from pipeline import _is_continuity_reel, _wan_length_for_seconds
from utils import build_lofi_echo_bed
import wave
import numpy as np
from pathlib import Path


def test_echo_chamber_raw_screenplay():
    topic = (
        'Generate a 12-second cinematic Reel exploring a modern "Echo Chamber" romance concept. '
        "A dynamic vertical split-screen. Left side maritime map forum. "
        "Right side penthouse balcony. At 8 seconds collapse into museum map exhibit. "
        "[TEXT OVERLAY] When the only one who understands your obsession, finally understands you. 🗺️💫 [/TEXT OVERLAY]"
    )
    job = TopicJob(topic=topic, director_mode="raw")
    sp = generate_screenplay(job)
    assert sp.raw.get("reel_profile") == "echo_chamber_12s"
    assert sp.raw.get("llm_disabled") is True
    assert sp.raw.get("continuity_i2v") is False
    assert sp.raw.get("collapse_at_sec") == 8.0
    assert sp.raw.get("burn_captions") is False
    assert len(sp.scenes) == 3
    assert sp.raw.get("compose_plan")[0]["type"] == "vsplit"
    assert sp.raw.get("beat_durations") == [8.0, 8.0, 3.9]
    assert "single subject only" in sp.scenes[0].visual_prompt.lower()
    assert "museum" in sp.scenes[2].visual_prompt.lower()
    assert _is_continuity_reel(job, sp) is False
    assert _wan_length_for_seconds(8.0) == 128
    assert _wan_length_for_seconds(3.9) == 62


def test_lofi_bed_chime_and_mute(tmp_path: Path):
    out = tmp_path / "lofi.wav"
    build_lofi_echo_bed(11.9, collapse_at=8.0, out_path=out, loop_end_silence=0.5)
    with wave.open(str(out), "rb") as wf:
        sr = wf.getframerate()
        mono = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32)
    tail = mono[int(-0.5 * sr) :]
    assert float(np.max(np.abs(tail))) == 0.0
    hit = mono[int(8.0 * sr) : int(8.3 * sr)]
    assert float(np.max(np.abs(hit))) > 1000
