"""Raw / Reel precision lockdown: LLM off, overlay, clock prop, continuity, mute tail."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

import config
from director import (
    TopicJob,
    extract_text_overlay,
    generate_screenplay,
    parse_topic_line,
)
from pipeline import _inject_reel_prop_lock, _is_continuity_reel, _scene_negative
from utils import build_analog_horror_bed


def test_mode_raw_disables_llm_and_locks_overlay():
    job = parse_topic_line(
        "mode:raw | POV dark bedroom phone clock 25:66 analog horror "
        "[TEXT OVERLAY] Check your phone. Time is running out. [/TEXT OVERLAY]"
    )
    assert job is not None
    assert job.director_mode == "raw"
    assert extract_text_overlay(job.topic) == "Check your phone. Time is running out."
    sp = generate_screenplay(job)
    assert sp.raw.get("llm_disabled") is True
    assert sp.raw.get("continuity_i2v") is False
    assert sp.raw.get("text_overlay") == "Check your phone. Time is running out."
    assert all(s.narration == sp.raw["text_overlay"] for s in sp.scenes)
    assert "forgets how" not in " ".join(s.narration for s in sp.scenes).lower()


def test_cli_raw_analog_fallback_uses_same_overlay():
    job = TopicJob(
        topic="POV dark minimalist bedroom nightstand smartphone lock screen 25:66 analog horror",
        director_mode="raw",
    )
    sp = generate_screenplay(job)
    assert sp.raw.get("reel_profile") == "analog_phone_12s"
    assert sp.raw.get("caption_position") == "top"
    assert "circular" in (sp.prop_bible or "").lower() or "HH:MM" in sp.scenes[0].visual_prompt
    assert "03:14" in sp.scenes[0].visual_prompt
    assert "ONLY normal time 03:14" in sp.scenes[0].visual_prompt
    assert "impossible time 25:66" in sp.scenes[1].visual_prompt
    assert "handheld" not in sp.scenes[1].visual_prompt.lower() or "no handheld" in sp.scenes[1].visual_prompt.lower()
    assert _is_continuity_reel(job, sp) is False


def test_clock_and_continuity_prompt_injection():
    vis = _inject_reel_prop_lock("dark bedroom phone", continuity=True)
    assert "HH:MM" in vis
    assert "locked off camera" in vis.lower()
    neg = _scene_negative(config.FLUX_NEGATIVE_PROMPT, reel_continuity=True)
    assert "circular clock" in neg
    assert "handheld" in neg
    assert "blown-out glowing numbers" in config.FLUX_NEGATIVE_PROMPT


def test_caption_wrap_width_25_fontsize_48():
    assert int(config.CAPTION_TEXTWRAP_WIDTH) == 25
    assert int(config.CAPTION_FONTSIZE) == 48
    assert float(config.REEL_LOOP_END_SILENCE) == 0.5
    assert float(config.RAW_CAPTION_Y_REL) == 0.15


def test_analog_bed_mutes_final_half_second(tmp_path: Path):
    out = tmp_path / "bed.wav"
    build_analog_horror_bed(11.9, glitch_at=6.0, out_path=out, loop_end_silence=0.5)
    with wave.open(str(out), "rb") as wf:
        sr = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
        mono = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    tail = mono[int(-0.5 * sr) :]
    assert float(np.max(np.abs(tail))) == 0.0
    # Glitch window still has energy
    g0 = int(6.0 * sr)
    glitch = mono[g0 : g0 + int(0.3 * sr)]
    assert float(np.max(np.abs(glitch))) > 1000
