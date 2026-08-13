"""Locked wingsuit 15s one-shot continuity Reel."""
from pathlib import Path

import numpy as np
from PIL import Image

from director import TopicJob, generate_screenplay
from pipeline import (
    _bump_wan_sampler_steps,
    _is_continuity_reel,
    _scene_negative,
    _scene_visual_for_flux,
    _score_suit_bible_still,
)
import config


def test_wingsuit_oneshot_locked_screenplay():
    job = TopicJob(
        topic=(
            "A high-octane cinematic wingsuit flyer soaring through a narrow "
            "jagged mountain canyon, first-person POV then drone tracking"
        ),
        director_mode="story",
        ratio="9:16",
    )
    sp = generate_screenplay(job)
    assert sp.raw.get("reel_profile") == "wingsuit_oneshot_15s"
    assert sp.raw.get("llm_disabled") is True
    assert sp.raw.get("skip_act_emotion") is True
    assert sp.raw.get("action_flight") is True
    assert sp.raw.get("continuity_i2v") is True
    assert sp.raw.get("burn_captions") is False
    assert sp.raw.get("fpv_scene_indices") == []
    assert len(sp.scenes) == 3
    assert sp.raw.get("beat_durations") == [5.0, 5.0, 5.0]
    assert "continuous" in sp.scenes[0].visual_prompt.lower() or "drone chase" in sp.scenes[0].visual_prompt.lower()
    assert "FORBIDDEN" in sp.character_bible
    assert "fabric" in sp.character_bible.lower() or "nylon" in sp.character_bible.lower()
    assert _is_continuity_reel(job, sp) is True
    neg = _scene_negative(config.FLUX_NEGATIVE_PROMPT, action_flight=True)
    assert "butterfly wings" in neg.lower()
    assert "feathered wings" in neg.lower()
    assert int(getattr(config, "REEL_WAN_HIRES_LENGTH_CAP", 99)) <= 65
    assert int(getattr(config, "ACTION_FPV_STILL_CANDIDATES", 1)) >= 1
    w, h = config.WAN_SIZES["9:16"]
    assert w == 480 and h == 832


def test_wingsuit_skips_act2_emotion_injection():
    job = TopicJob(topic="wingsuit canyon flyer drone POV", director_mode="story")
    sp = generate_screenplay(job)
    vis = _scene_visual_for_flux(sp.scenes[1], idx=1, total=3, screenplay=sp, topic=job.topic)
    assert "looking away" not in vis.lower()
    assert "sad expression" not in vis.lower()


def test_oneshot_keeps_character_bible_on_all_beats():
    job = TopicJob(topic="wingsuit canyon flyer drone POV", director_mode="story")
    sp = generate_screenplay(job)
    for i, sc in enumerate(sp.scenes):
        vis = _scene_visual_for_flux(sc, idx=i, total=3, screenplay=sp, topic=job.topic)
        assert "SAME wingsuit flyer" in vis or "CHARACTER_BIBLE" in vis


def test_wan_sizes_configured():
    w, h = config.WAN_SIZES["9:16"]
    assert w >= 480 and h >= 832
    assert config.WAN_SIZES["16:9"][0] >= 832


def test_suit_bible_flag_and_quality_knobs():
    job = TopicJob(topic="wingsuit canyon flyer drone POV", director_mode="story")
    sp = generate_screenplay(job)
    assert "suit_bible" in sp.raw
    assert int(getattr(config, "ACTION_SUIT_BIBLE_CANDIDATES", 0)) >= 1
    assert int(getattr(config, "WAN_QUALITY_STEPS", 0)) >= 14
    assert "nylon" in getattr(config, "ACTION_SUIT_BIBLE_PROMPT", "").lower()


def test_score_suit_bible_prefers_dark_body_over_orange_wings(tmp_path: Path):
    dark = tmp_path / "tech.png"
    fant = tmp_path / "butterfly.png"
    arr_d = np.zeros((168, 96, 3), dtype=np.uint8)
    arr_d[:, :] = (25, 25, 28)
    arr_d[70:110, 35:60] = (18, 18, 20)
    arr_d[88:92, 28:34] = (200, 90, 30)
    Image.fromarray(arr_d, "RGB").save(dark)
    arr_f = np.zeros((168, 96, 3), dtype=np.uint8)
    arr_f[:, :] = (40, 40, 45)
    arr_f[45:130, 8:40] = (220, 70, 15)
    arr_f[45:130, 56:88] = (220, 70, 15)
    Image.fromarray(arr_f, "RGB").save(fant)
    assert _score_suit_bible_still(dark) > _score_suit_bible_still(fant)


def test_bump_wan_sampler_steps_splits_high_low():
    wf = {
        "22": {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "add_noise": "enable",
                "steps": 14,
                "end_at_step": 7,
                "start_at_step": 0,
            },
        },
        "23": {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "add_noise": "disable",
                "steps": 14,
                "start_at_step": 7,
                "end_at_step": 10000,
            },
        },
    }
    _bump_wan_sampler_steps(wf, 20)
    assert wf["22"]["inputs"]["steps"] == 20
    assert wf["22"]["inputs"]["end_at_step"] == 10
    assert wf["23"]["inputs"]["steps"] == 20
    assert wf["23"]["inputs"]["start_at_step"] == 10
