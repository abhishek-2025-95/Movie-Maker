"""9/10 polish guards: LLM retries, eyeline negatives, caption lock, sharpness."""
from __future__ import annotations

import config
from director import HOLLYWOOD_DIRECTOR_SYSTEM_PROMPT, style_prompts
from pipeline import _scene_visual_for_flux
from director import Scene


def test_ollama_retries_at_least_three():
    assert int(getattr(config, "OLLAMA_MAX_RETRIES", 0)) >= 3


def test_eyeline_in_global_negative():
    _, neg = style_prompts("live")
    assert "looking at camera" in neg
    assert "portrait shot" in neg
    assert "eye contact with viewer" in neg


def test_director_prompt_bans_camera_eyeline():
    p = HOLLYWOOD_DIRECTOR_SYSTEM_PROMPT.lower()
    assert "never looking at the camera" in p or "never look into the lens" in p
    assert "eyeline" in p
    assert "facing the camera" in p or "face the camera" in p

def test_caption_bottom_and_stroke_config():
    assert int(config.CAPTION_STROKE_WIDTH) == 2
    assert int(config.CAPTION_FONTSIZE) == 48
    assert int(config.CAPTION_TEXTWRAP_WIDTH) >= 24
    assert int(getattr(config, "CAPTION_MAX_LINES", 0)) == 3


def test_visual_sharpness_appended_before_flux():
    sc = Scene(
        narration="x",
        visual_prompt="server aisle tension",
        motion_prompt="slow push",
    )
    vis = _scene_visual_for_flux(sc, idx=0, total=3).lower()
    assert "ultra-sharp focus" in vis
    assert "crisp cinematic lighting" in vis


def test_eyeline_lookback_negative():
    _, neg = style_prompts("live")
    assert "looking back" in neg
    assert "over shoulder" in neg
