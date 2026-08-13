"""Transition mapping + stitch guards."""
from __future__ import annotations

import config
from director import TopicJob, generate_screenplay, normalize_transition


def test_normalize_transition_aliases():
    assert normalize_transition("cross_fade") == "crossfade"
    assert normalize_transition("fade") == "fade_to_black"
    assert normalize_transition("smash") == "smash_cut"
    assert normalize_transition("garbage") == "hard_cut"
    assert normalize_transition("crossfade", is_last=True) == "none"


def test_love_screenplay_has_distinct_acts_and_transitions():
    job = TopicJob(
        topic="Mumbai Rain Metro Love Story",
        mode="character",
        style="live",
        ratio="9:16",
        lang="en",
    )
    sp = generate_screenplay(job)
    assert len(sp.scenes) == 8
    assert sp.scenes[-1].transition_to_next == "none"
    assert sp.scenes[0].transition_to_next == "crossfade"
    assert sp.scenes[3].transition_to_next == "fade_to_black"
    # Distinct locations / story beats in visual prompts
    v0, v3, v5 = (sp.scenes[i].visual_prompt.lower() for i in (0, 3, 5))
    assert "metro" in v0 or "umbrella" in v0
    assert "rooftop" in v3 or "bandra" in v3
    assert "hold hands" in v5 or "reunion" in v5 or "platform" in v5
    assert v0 != v3 != v5


def test_master_still_lock_disabled_for_3act():
    assert getattr(config, "CHARACTER_MASTER_STILL_LOCK", True) is False
