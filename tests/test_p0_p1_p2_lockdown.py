"""P0/P1/P2 lockdown: captions, Dynamic Trinity, Act-3 emotion, VO, InstantX."""
from __future__ import annotations

import config
from director import (
    HOLLYWOOD_DIRECTOR_SYSTEM_PROMPT,
    Scene,
    Screenplay,
    _extract_trinity,
    _parse_screenplay,
    style_prompts,
    topic_implies_solitary,
)
from pipeline import (
    _enforce_narration_density,
    _prepend_trinity,
    _scene_negative,
    _scene_visual_for_flux,
)


def test_caption_p0_params():
    assert config.CAPTION_COLOR == "white"
    assert config.CAPTION_STROKE == "black"
    assert int(config.CAPTION_STROKE_WIDTH) == 2
    assert int(config.CAPTION_FONTSIZE) == 48
    assert int(config.CAPTION_TEXTWRAP_WIDTH) >= 24


def test_eyeline_lookback_in_negative():
    _, neg = style_prompts("live")
    assert "looking back" in neg
    assert "over shoulder" in neg
    assert "facing camera" in neg


def test_act3_emotion_negative():
    neg = _scene_negative(config.FLUX_NEGATIVE_PROMPT, is_act3=True)
    assert "smiling" in neg and "happy" in neg and "relaxed" in neg


def test_topic_solitary_detect():
    assert topic_implies_solitary(
        "A solitary archaeologist discovering a glowing artifact in an Egyptian tomb."
    )
    assert not topic_implies_solitary("A tense neo-noir detective stakeout")


def test_trinity_extract_and_prepend():
    data = {
        "title": "Tomb",
        "character_bible": "solitary woman archaeologist dusty tan jacket",
        "location_lock": "dust-filled Egyptian tomb sandstone",
        "prop_bible": "brass gears, pulsing mechanical core",
        "scenes": [
            {
                "narration": "Dust settles soft across the forgotten chamber as she kneels alone before fate.",
                "visual_prompt": "profile looking at relic",
                "motion_prompt": "slow push",
                "transition_to_next": "hard_cut",
            }
        ],
    }
    sp = _parse_screenplay(data, "tomb topic solitary archaeologist", style="live")
    assert "solitary" in sp.character_bible.lower() or "archaeologist" in sp.character_bible.lower()
    assert "tomb" in sp.location_lock.lower()
    assert "brass" in sp.prop_bible.lower() or "mechanical" in sp.prop_bible.lower()
    vis = _scene_visual_for_flux(sp.scenes[0], idx=0, total=3, screenplay=sp, topic=data["title"] + " solitary")
    assert "LOCATION_LOCK:" in vis
    assert "PROP_BIBLE:" in vis
    assert "CHARACTER_BIBLE:" in vis


def test_vo_bans_generic_filler():
    scenes = [
        Scene(narration="Short line.", visual_prompt="a", motion_prompt="m"),
        Scene(narration="Also short.", visual_prompt="b", motion_prompt="m"),
        Scene(narration="Tiny.", visual_prompt="c", motion_prompt="m"),
    ]
    out = _enforce_narration_density(
        scenes,
        topic="A solitary archaeologist in a dust-filled Egyptian tomb",
    )
    blob = " ".join(s.narration.lower() for s in out)
    assert "every second counts" not in blob
    assert "truth refuses to stay buried" not in blob
    assert "sand drifts through the dark" not in blob
    for s in out:
        n = len(s.narration.split())
        assert 15 <= n <= 20
        assert ". " not in s.narration  # single complete line, no pad glue


def test_director_prompt_trinity_and_vo():
    p = HOLLYWOOD_DIRECTOR_SYSTEM_PROMPT.lower()
    assert "character_bible" in p
    assert "location_lock" in p
    assert "prop_bible" in p
    assert "every second counts" in p  # banned by instruction
    assert "15 to 20" in p


def test_instantx_off_by_default():
    assert getattr(config, "ENABLE_INSTANTX", True) is False
    assert getattr(config, "INSTANTX_REQUIRES_VRAM_FLUSH", False) is True


def test_trinity_fallback_keys():
    char, loc, prop, light = _extract_trinity({}, "solitary archaeologist egyptian tomb artifact")
    assert "archaeologist" in char.lower() or "solitary" in char.lower()
    assert "tomb" in loc.lower()
    assert "mechanical" in prop.lower() or "brass" in prop.lower()
    assert "rembrandt" in light.lower() or "oil" in light.lower() or "shadow" in light.lower()


def test_prepend_idempotent():
    sp = Screenplay(
        title="t",
        character_bible="hero",
        location_lock="tomb",
        prop_bible="relic",
        lighting_bible="oil lamp rembrandt",
    )
    once = _prepend_trinity("shot", sp)
    twice = _prepend_trinity(once, sp)
    assert twice.count("LOCATION_LOCK:") == 1
    assert "LIGHTING_BIBLE:" in once
    assert "SENSORY_BIBLE:" in once
    assert "microscopic dust" in once.lower() or "weathered" in once.lower()
