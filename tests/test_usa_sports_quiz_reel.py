"""Locked USA sports quiz 12s Reel."""
from director import TopicJob, generate_screenplay
from pipeline import _is_continuity_reel, _scene_visual_for_flux, _wan_length_for_seconds


def test_usa_sports_quiz_locked_screenplay():
    job = TopicJob(
        topic="USA Sports quiz Reel — NFL Super Bowl trivia",
        director_mode="story",
        ratio="9:16",
        lang="en",
    )
    sp = generate_screenplay(job)
    assert sp.raw.get("reel_profile") == "usa_sports_quiz_12s"
    assert sp.raw.get("llm_disabled") is True
    assert sp.raw.get("skip_act_emotion") is True
    assert sp.raw.get("burn_captions") is True
    assert sp.raw.get("caption_mode") == "per_beat"
    assert sp.raw.get("caption_position") == "center"
    assert sp.raw.get("continuity_i2v") is False
    assert sp.raw.get("beat_durations") == [5.0, 4.0, 3.0]
    assert len(sp.scenes) == 3
    assert "Super Bowl" in sp.scenes[0].narration
    assert "Patriots" in sp.scenes[1].narration
    assert "Steelers" in sp.scenes[2].narration
    assert "6" in sp.scenes[2].narration
    assert _is_continuity_reel(job, sp) is False
    assert _wan_length_for_seconds(5.0) >= 65


def test_usa_sports_quiz_skips_act2_emotion():
    job = TopicJob(topic="US sports trivia quiz NFL", director_mode="story")
    sp = generate_screenplay(job)
    vis = _scene_visual_for_flux(sp.scenes[1], idx=1, total=3, screenplay=sp, topic=job.topic)
    assert "looking away" not in vis.lower()
    assert "sad expression" not in vis.lower()
    assert "stadium" in vis.lower()
    assert "trench coat" not in vis.lower()
    assert "CHARACTER_BIBLE" not in vis
    assert sp.raw.get("skip_character_bible") is True


def test_usa_sports_quiz_raw_mode_also_locks():
    job = TopicJob(topic="American sports quiz Super Bowl", director_mode="raw")
    sp = generate_screenplay(job)
    assert sp.raw.get("reel_profile") == "usa_sports_quiz_12s"
