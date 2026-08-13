"""True split + face fill + Wan sharpness protocol."""
from __future__ import annotations

import config
from director import TopicJob, generate_screenplay
from pipeline import _inject_face_fill, _scene_negative
from utils import compose_vertical_split


def test_echo_chamber_true_split_compose_plan():
    job = TopicJob(
        topic='Echo Chamber romance split-screen maritime map forum penthouse balcony',
        director_mode="raw",
    )
    sp = generate_screenplay(job)
    assert len(sp.scenes) == 3
    assert sp.raw.get("compose_plan")
    plan = sp.raw["compose_plan"]
    assert plan[0]["type"] == "vsplit"
    assert plan[0]["sources"] == [0, 1]
    assert plan[1]["type"] == "single"
    assert plan[1]["sources"] == [2]
    specs = sp.raw["panel_specs"]
    assert specs[0]["ratio"] == "16:9"
    assert specs[1]["ratio"] == "16:9"
    assert specs[2]["ratio"] == "9:16"
    assert "single subject only" in sp.scenes[0].visual_prompt.lower()
    assert "no split-screen" in sp.scenes[0].visual_prompt.lower()
    assert "soft front fill" in sp.scenes[2].visual_prompt.lower()
    assert "not silhouette" in sp.scenes[2].visual_prompt.lower()


def test_face_fill_and_silhouette_negatives():
    assert "silhouette" in config.FLUX_NEGATIVE_PROMPT
    assert "soft front fill light" in config.FACE_FILL_POSITIVE
    vis = _inject_face_fill("museum reunion two people")
    assert "soft front fill light" in vis
    neg = _scene_negative(config.FLUX_NEGATIVE_PROMPT, face_fill=True)
    assert "hidden face" in neg
    assert "underexposed" in neg


def test_wan_resolution_bumped():
    assert config.WAN_SIZES["9:16"][0] >= 480
    assert config.WAN_SIZES["16:9"][0] >= 832
    assert getattr(config, "FORCE_GC_BEFORE_WAN", False) is True
    assert int(getattr(config, "REEL_WAN_HIRES_LENGTH_CAP", 99)) <= 96


def test_compose_vertical_split_shape():
    import numpy as np
    from moviepy.editor import ImageClip

    top = ImageClip(np.zeros((480, 832, 3), dtype=np.uint8) + 40).set_duration(1.0)
    bot = ImageClip(np.zeros((480, 832, 3), dtype=np.uint8) + 80).set_duration(1.0)
    stacked = compose_vertical_split(top, bot, out_w=768, out_h=1344, duration=1.0)
    assert stacked.w == 768
    assert stacked.h == 1344
    assert abs(float(stacked.duration) - 1.0) < 0.05
    top.close()
    bot.close()
    stacked.close()
