"""Locked full-song lyric music video (music_video_lyric_180s)."""
from pathlib import Path

from PIL import Image

from director import TopicJob, generate_screenplay
from pipeline import _scene_visual_for_flux
from utils import ken_burns_clip, load_lyric_cues


def test_music_video_lyric_locked_screenplay():
    job = TopicJob(
        topic="music video lyric I Never Said It Out Loud FINAL_HIT_SONG",
        director_mode="story",
        ratio="16:9",
        lang="en",
    )
    sp = generate_screenplay(job)
    assert sp.raw.get("reel_profile") == "music_video_lyric_180s"
    assert sp.raw.get("llm_disabled") is True
    assert sp.raw.get("skip_character_bible") is True
    assert sp.raw.get("burn_captions") is True
    assert sp.raw.get("caption_mode") == "lyric_cues"
    assert sp.raw.get("master_audio")
    assert sp.raw.get("lyric_alignment")
    assert sp.raw.get("target_duration_sec") == 180.0
    assert len(sp.scenes) == 12
    durs = sp.raw.get("beat_durations") or []
    assert len(durs) == 12
    assert abs(sum(float(d) for d in durs) - 180.0) < 0.2
    engines = [b.get("engine") for b in (sp.raw.get("beat_plan") or [])]
    assert "wan" in engines and "ken_burns" in engines
    assert engines.count("wan") >= 5


def test_music_video_skips_romance_duo_bible():
    job = TopicJob(
        topic="music_video_lyric_180s FINAL_HIT_SONG",
        director_mode="story",
        ratio="16:9",
    )
    sp = generate_screenplay(job)
    vis = _scene_visual_for_flux(sp.scenes[0], idx=0, total=12, screenplay=sp, topic=job.topic)
    assert "trench coat" not in vis.lower()
    assert "SAME young man" in vis
    assert "no letterbox" in vis.lower()
    assert sp.raw.get("mv_version") == 2


def test_music_video_v2_distinct_locations():
    job = TopicJob(topic="FINAL_HIT_SONG music video", director_mode="story", ratio="16:9")
    sp = generate_screenplay(job)
    blob = " | ".join(s.visual_prompt.lower() for s in sp.scenes)
    assert "train" in blob or "metro" in blob or "subway" in blob
    assert "doorway" in blob or "threshold" in blob
    assert "hallway" in blob
    assert ("rooftop" in blob) or ("fire-escape" in blob) or ("sidewalk" in blob)
    train = next(
        s for s in sp.scenes if "train" in s.visual_prompt.lower() or "metro" in s.visual_prompt.lower()
    )
    assert "forbidden" in train.visual_prompt.lower()


def test_load_lyric_cues():
    cues = load_lyric_cues(r"C:\Users\user\Documents\SunoX\workspace\lyric_alignment.json")
    assert len(cues) >= 40
    assert cues[0]["text"]
    assert cues[0]["end"] > cues[0]["start"]


def test_ken_burns_duration(tmp_path: Path):
    p = tmp_path / "s.png"
    Image.new("RGB", (1344, 768), (20, 30, 40)).save(p)
    clip = ken_burns_clip(p, duration=5.0, out_w=1920, out_h=1080)
    assert abs(float(clip.duration) - 5.0) < 0.05
    clip.close()


def test_lyric_cues_in_window():
    from editor import _lyric_cues_in_window

    cues = [
        {"start": 1.0, "end": 3.0, "text": "Hello"},
        {"start": 10.0, "end": 12.0, "text": "World"},
    ]
    mid = _lyric_cues_in_window(cues, t0=0.0, t1=5.0)
    assert len(mid) == 1 and mid[0]["text"] == "Hello"
