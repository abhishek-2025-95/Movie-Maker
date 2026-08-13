"""Scorecard lock-down guards (Act-2 emotion, bible, captions, Wan length)."""
from __future__ import annotations

import textwrap

import config
from director import TopicJob, generate_screenplay
from pipeline import _apply_character_bible, _scene_negative


def test_pycaps_disabled():
    assert getattr(config, "USE_PYCAPS", True) is False


def test_wan_length_five_seconds():
    assert config.WAN_LENGTH == 81
    assert config.WAN_SIZES["9:16"] == (576, 1024)
    assert config.WAN_SIZES["16:9"] == (1024, 576)


def test_character_bible_prepended():
    bible = config.CHARACTER_BIBLE
    out = _apply_character_bible("ACT1 metro umbrella")
    assert out.startswith(bible)
    assert "metro umbrella" in out


def test_act2_negative_and_emotion_keywords():
    job = TopicJob(topic="Mumbai Rain Metro Love Story", mode="character", style="live")
    sp = generate_screenplay(job)
    assert len(sp.scenes) == 8
    assert sp.raw.get("skip_act_emotion") is True
    # Solitary ache beat is locked in the screenplay (index 3)
    vis = sp.scenes[3].visual_prompt.lower()
    assert "looking away" in vis or "solitary" in vis or "sad expression" in vis
    assert "alone" in vis or "isolated" in vis or "no other characters" in vis
    # Act-2 negative bank still available when explicitly requested
    neg = _scene_negative(config.FLUX_NEGATIVE_PROMPT, is_act2=True)
    assert "smiling" in neg and "happy" in neg and "eye contact" in neg and "together" in neg


def test_textwrap_caption_width():
    s = textwrap.fill("One missed call. A whole city between them.", width=18)
    assert all(len(line) <= 18 for line in s.splitlines())


def test_ollama_num_gpu_zero():
    assert int(getattr(config, "OLLAMA_NUM_GPU", 1)) == 0
