"""9.0 blockers: caption fit, Act-3 location, prop wide, VO no pad clauses."""
from __future__ import annotations

import config
from director import Scene, Screenplay, _enrich_visual_prompt
from editor import _wrap_caption_fit
from pipeline import (
    _enforce_narration_density,
    _scene_negative,
    _scene_visual_for_flux,
)


def test_caption_wrap_fits_three_lines_no_mid_cut():
    text = (
        "Sandstorms have swallowed the past, leaving only whispers in the wind "
        "across the forgotten chamber."
    )
    wrapped = _wrap_caption_fit(
        text,
        wrap_w=int(config.CAPTION_TEXTWRAP_WIDTH),
        max_lines=int(config.CAPTION_MAX_LINES),
    )
    assert wrapped
    assert len(wrapped.splitlines()) <= int(config.CAPTION_MAX_LINES)
    assert not wrapped.rstrip().endswith(("the", "of", "in", "only", "a"))
    assert int(config.CAPTION_FONTSIZE) <= 50
    assert int(config.CAPTION_TEXTWRAP_WIDTH) >= 24


def test_act3_location_negative_bans_modern_strips():
    neg = _scene_negative(config.FLUX_NEGATIVE_PROMPT, is_act3=True)
    assert "LED wall strips" in neg or "sci-fi light bars" in neg
    assert "modern fluorescent" in neg


def test_prop_wide_visibility_injected():
    sp = Screenplay(
        title="tomb",
        character_bible="solitary archaeologist",
        location_lock="dust-filled Egyptian tomb sandstone",
        prop_bible="brass gears pulsing mechanical core",
        scenes=[],
    )
    sc = Scene(
        narration="x",
        visual_prompt="wide shot down corridor",
        motion_prompt="hold",
    )
    vis = _scene_visual_for_flux(
        sc, idx=0, total=3, screenplay=sp, topic="solitary archaeologist egyptian tomb"
    ).lower()
    assert "brass gears" in vis or "featureless glowing orb" in vis
    assert "prop clearly readable" in vis or "mechanical" in vis


def test_act3_reinforces_location_lock():
    sp = Screenplay(
        title="tomb",
        character_bible="solo",
        location_lock="dust-filled Egyptian tomb sandstone corridor",
        prop_bible="mechanical core",
        scenes=[],
    )
    sc = Scene(narration="x", visual_prompt="climax wide", motion_prompt="pull back")
    vis = _scene_visual_for_flux(
        sc, idx=2, total=3, screenplay=sp, topic="egyptian tomb artifact"
    ).lower()
    assert "location_lock reinforced" in vis
    assert "hieroglyph" in vis or "sandstone" in vis
    assert "no modern lighting" in vis


def test_vo_strips_density_pad_second_clause():
    scenes = [
        Scene(
            narration=(
                "Sandstorms have swallowed the past, leaving only whispers in the wind. "
                "Sand drifts through the dark as the forgotten chamber"
            ),
            visual_prompt="a",
            motion_prompt="m",
        ),
        Scene(
            narration=(
                "In forgotten chambers, secrets slumber. "
                "Dust thickens while something ancient begins"
            ),
            visual_prompt="b",
            motion_prompt="m",
        ),
        Scene(
            narration="The winds of time howl through the corridors, warning of a truth that cannot be contained.",
            visual_prompt="c",
            motion_prompt="m",
        ),
    ]
    out = _enforce_narration_density(
        scenes, topic="A solitary archaeologist in an Egyptian tomb artifact"
    )
    blob = " | ".join(s.narration.lower() for s in out)
    assert "sand drifts through the dark" not in blob
    assert "dust thickens while something ancient" not in blob
    for s in out:
        assert ". " not in s.narration or s.narration.count(". ") == 0
        n = len(s.narration.split())
        assert 15 <= n <= 20
        assert s.narration.rstrip().endswith((".", "!", "?"))


def test_enrich_no_romance_from_gloves_substring():
    out = _enrich_visual_prompt(
        "archaeologist in dusty leather gloves",
        "she kneels in the tomb",
        "egyptian tomb solitary artifact",
        style="live",
    ).lower()
    assert "romantic atmosphere" not in out
    assert "oil-lamp" in out or "torch" in out
    assert "fluorescent" not in out
