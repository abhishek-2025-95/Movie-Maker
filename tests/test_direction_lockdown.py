"""Final direction/editing lockdowns: VO density, Act-2 isolation, caption hard-stop."""
from __future__ import annotations

import config
from director import Scene, TopicJob, generate_screenplay
from pipeline import (
    _apply_character_bible,
    _enforce_narration_density,
    _is_act2_scene,
    _scene_visual_for_flux,
)


def test_narration_density_and_uniqueness():
    scenes = [
        Scene(narration="Too short.", visual_prompt="a", motion_prompt="m"),
        Scene(narration="Too short.", visual_prompt="b", motion_prompt="m"),
        Scene(narration="Also short line.", visual_prompt="c", motion_prompt="m"),
    ]
    out = _enforce_narration_density(scenes)
    texts = [s.narration.lower() for s in out]
    assert len(set(texts)) == 3
    for s in out:
        n = len(s.narration.split())
        assert n >= config.NARRATION_MIN_WORDS
        assert n <= config.NARRATION_MAX_WORDS


def test_act2_isolates_single_character():
    sc = Scene(
        narration="x",
        visual_prompt="neon alley stakeout tension",
        motion_prompt="slow push",
    )
    vis = _scene_visual_for_flux(sc, idx=1, total=3).lower()
    assert "solitary shot of only" in vis
    assert "no other characters" in vis
    assert _is_act2_scene(1, sc, 3) is True
    # Full duo bible should not be forced as a pair requirement in Act 2
    duo = config.CHARACTER_BIBLE.lower()
    # Isolation line must mention only one bible half
    assert config.CHARACTER_BIBLE_A.lower() in vis or config.CHARACTER_BIBLE_B.lower() in vis


def test_act1_keeps_duo_bible():
    sc = Scene(narration="x", visual_prompt="establishing alley", motion_prompt="hold")
    vis = _apply_character_bible(sc.visual_prompt, is_act2=False).lower()
    assert "tan trench" in vis
    assert "short beard" in vis or "dark green" in vis


def test_caption_fade_and_end_hold_config():
    assert float(config.CAPTION_FADEOUT_SEC) == 0.5
    assert float(config.END_BLACK_HOLD_SEC) == 1.0


def test_director_prompt_requires_dense_unique_vo():
    from director import HOLLYWOOD_DIRECTOR_SYSTEM_PROMPT

    p = HOLLYWOOD_DIRECTOR_SYSTEM_PROMPT.lower()
    assert "15 to 20" in p
    assert "forbidden from repeating" in p
    assert "solitary" in p
    assert "character_bible" in p
    assert "location_lock" in p
    assert "prop_bible" in p