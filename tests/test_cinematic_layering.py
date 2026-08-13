"""Cinematic Detail & Sensory Layering guards."""
from __future__ import annotations

import numpy as np

import config
from director import HOLLYWOOD_DIRECTOR_SYSTEM_PROMPT, Screenplay, Scene, _extract_trinity
from pipeline import _prepend_trinity, _scene_visual_for_flux
from utils import apply_cinematic_layering


def test_sensory_bible_config():
    s = config.SENSORY_BIBLE.lower()
    assert "weathered" in s
    assert "microscopic dust" in s
    assert "god-rays" in s or "god rays" in s
    assert "chromatic aberration" in s


def test_director_prompt_quad_and_sensory():
    p = HOLLYWOOD_DIRECTOR_SYSTEM_PROMPT.lower()
    assert "lighting_bible" in p
    assert "sensory" in p
    assert "chiaroscuro" in p or "rembrandt" in p


def test_lighting_bible_in_extract_and_prepend():
    data = {
        "character_bible": "solo archaeologist",
        "location_lock": "egyptian tomb",
        "prop_bible": "brass core",
        "lighting_bible": "flickering oil lamp, Rembrandt lighting, deep shadows",
        "scenes": [],
    }
    char, loc, prop, light = _extract_trinity(data, "tomb")
    assert "oil lamp" in light.lower()
    sp = Screenplay(
        title="t",
        character_bible=char,
        location_lock=loc,
        prop_bible=prop,
        lighting_bible=light,
    )
    vis = _prepend_trinity("wide shot", sp)
    assert "LIGHTING_BIBLE:" in vis
    assert "SENSORY_BIBLE:" in vis


def test_scene_visual_gets_sensory_and_lighting():
    sp = Screenplay(
        title="tomb",
        character_bible="solo",
        location_lock="dust-filled Egyptian tomb",
        prop_bible="mechanical core",
        lighting_bible="oil lamp Rembrandt chiaroscuro",
    )
    sc = Scene(narration="x", visual_prompt="corridor", motion_prompt="push")
    vis = _scene_visual_for_flux(
        sc, idx=0, total=3, screenplay=sp, topic="solitary archaeologist egyptian tomb"
    ).lower()
    assert "lighting_bible" in vis
    assert "sensory_bible" in vis
    assert "microscopic dust" in vis or "weathered" in vis


def test_cinematic_layering_transforms_frame():
    from moviepy.editor import ColorClip

    assert getattr(config, "ENABLE_CINEMATIC_LAYERING", False) is True
    base = ColorClip(size=(64, 96), color=(120, 100, 80), duration=0.2).set_fps(24)
    graded = apply_cinematic_layering(base)
    f0 = graded.get_frame(0.0)
    assert f0.shape == (96, 64, 3)
    # Not identical flat color — grain/vignette/grade altered pixels
    assert float(np.std(f0.astype(np.float32))) > 0.5
    base.close()
    graded.close()
