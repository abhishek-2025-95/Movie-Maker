"""US Brooklyn Stoop 10s romance — quality-first contract (no GPU)."""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config
from render_us_stoop_almost_10s import (
    BEATS,
    HERO_PROMPT,
    LOCK,
    MAN,
    NEG,
    OUT_H,
    OUT_W,
    SCENE,
    TARGET_SEC,
    WAN_LEN,
    WH,
    WOMAN,
    WW,
    XFADE_SEC,
    assert_quality_lock,
    build_romance_bed,
    make_plates,
    planned_duration_sec,
    quality_lock,
)


def test_ten_second_plan_is_exact():
    assert abs(planned_duration_sec() - 10.0) < 0.05
    assert TARGET_SEC == 10.0
    assert len(BEATS) == 2
    assert all(b["length"] == WAN_LEN for b in BEATS)
    assert abs(2 * (WAN_LEN / 16.0) - XFADE_SEC - 10.0) < 0.05


def test_quality_lock_max_path():
    q = quality_lock()
    assert q["quality_first"] is True
    assert q["two_pass"] is True
    assert q["wan_steps"] >= 14
    assert q["wan_cfg"] >= 4.0
    assert q["flux_steps"] >= 22
    assert q["freeze_pad"] is False
    assert q["ken_burns"] is False
    assert q["master_wh"] == [1920, 1080]
    assert q["wan_wh"] == [832, 480]
    assert q["aspect"] == "16:9"
    assert q["audience"] == "US"
    assert_quality_lock()


def test_us_audience_identity_and_location():
    blob = f"{LOCK} {SCENE} {HERO_PROMPT} {WOMAN} {MAN}".lower()
    assert "brooklyn" in blob
    assert "brownstone" in blob
    assert "american" in blob
    assert "same face" in blob
    assert "not kissing" in HERO_PROMPT.lower() or "not kissing" in blob
    assert "kissing" in NEG
    assert "identity morph" in NEG
    assert BEATS[0]["plate"] == "hero"
    assert BEATS[1]["plate"] == "hero_tight"
    for beat in BEATS:
        assert "identity locked" in beat["motion"]


def test_no_freeze_pad_config():
    assert getattr(config, "QUALITY_ALLOW_FREEZE_PAD", True) is False
    assert getattr(config, "QUALITY_ALLOW_KEN_BURNS_FALLBACK", True) is False
    assert int(getattr(config, "FLUX_STEPS", 0)) >= 22
    assert int(getattr(config, "WAN_QUALITY_STEPS", 0)) >= 14


def test_hero_plate_crops_reuse_pixels(tmp_path, monkeypatch):
    from PIL import Image

    import render_us_stoop_almost_10s as stoop

    monkeypatch.setattr(stoop, "WORK", tmp_path)
    hero = tmp_path / "hero.png"
    Image.new("RGB", (OUT_W // 2, OUT_H // 2), (180, 120, 80)).save(hero)
    plates = make_plates(hero)
    assert plates["hero"] == hero
    assert plates["hero_tight"].exists()
    tight = Image.open(plates["hero_tight"])
    assert tight.size == Image.open(hero).size


def test_romance_bed_is_stereo_and_alive(tmp_path):
    dest = tmp_path / "bed.wav"
    build_romance_bed(TARGET_SEC, dest)
    with wave.open(str(dest), "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getframerate() == 44100
        n = wf.getnframes()
        pcm = np.frombuffer(wf.readframes(n), dtype=np.int16).astype(np.float64)
    dur = n / 44100.0
    assert 9.9 <= dur <= 10.2
    rms = float(np.sqrt(np.mean((pcm / 32768.0) ** 2)))
    assert rms > 0.01, "bed is too quiet / empty"
    # Not a single pure sine: expect spectral spread
    left = pcm[0::2]
    spec = np.abs(np.fft.rfft(left[:44100]))
    peaks = int(np.sum(spec > (spec.max() * 0.08)))
    assert peaks >= 4
