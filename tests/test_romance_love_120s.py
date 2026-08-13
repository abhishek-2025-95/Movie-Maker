"""Locked 8-beat ~120s Mumbai rain romance reel."""
from __future__ import annotations

from director import TopicJob, generate_screenplay
from pipeline import _is_no_people_scene, _scene_visual_for_flux


def test_romance_love_120s_screenplay_lock():
    job = TopicJob(
        topic="Mumbai Rain Metro Love Story",
        mode="character",
        style="live",
        ratio="9:16",
        lang="en",
    )
    sp = generate_screenplay(job)
    assert len(sp.scenes) == 8
    assert sp.raw.get("reel_profile") == "romance_love_120s"
    assert sp.raw.get("target_duration_sec") == 120.0
    assert sp.raw.get("skip_act_emotion") is True
    assert sp.raw.get("burn_captions") is False
    assert sp.raw.get("mux_vo") is True
    durs = sp.raw.get("beat_durations") or []
    assert len(durs) == 8
    assert abs(sum(float(d) for d in durs) - 120.0) < 0.05
    assert sp.scenes[-1].transition_to_next == "none"
    blob = " ".join(s.visual_prompt.lower() for s in sp.scenes)
    assert "umbrella" in blob
    assert "rooftop" in blob or "bandra" in blob
    assert "hold hands" in blob or "joined hands" in blob
    assert "no kiss" in blob or "lips clearly apart" in blob


def test_romance_cutaways_are_no_people():
    job = TopicJob(topic="Mumbai Rain Metro Love Story", mode="character", style="live")
    sp = generate_screenplay(job)
    cutaways = [sp.scenes[2], sp.scenes[4]]
    for scene in cutaways:
        assert _is_no_people_scene(scene) is True
        vis = _scene_visual_for_flux(
            scene, idx=2, total=8, screenplay=sp, topic=job.topic
        ).lower()
        assert "character_bible" not in vis
    plan = sp.raw.get("beat_plan") or []
    assert all(p.get("engine") == "wan" for p in plan)
    assert len(plan) == 8
    assert sp.raw.get("require_wan") is True
    assert sp.raw.get("restart_comfy_before_wan") is True
