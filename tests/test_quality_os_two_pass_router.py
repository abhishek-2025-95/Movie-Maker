from pathlib import Path

import config
from pipeline_wan import (
    render_scene_wan_two_pass,
    should_use_two_pass,
    wan_quality_cfg,
    wan_quality_steps,
)


def test_two_pass_default():
    assert should_use_two_pass() is True
    assert wan_quality_steps() >= 14
    assert wan_quality_cfg() >= 4.0


def test_render_calls_two_pass(monkeypatch, tmp_path):
    calls = {}

    def fake_two_pass(still, **kwargs):
        calls.update(kwargs)
        out = kwargs["out_mp4"]
        out.write_bytes(b"fake")
        return out

    import sys

    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import wan_two_pass_moe

    monkeypatch.setattr(wan_two_pass_moe, "two_pass_wan", fake_two_pass)

    still = tmp_path / "s.png"
    still.write_bytes(b"x")
    out = render_scene_wan_two_pass(
        still=still,
        visual="v",
        motion="m",
        prefix="p",
        seed=1,
        neg="n",
        ww=480,
        wh=832,
        length=49,
        work=tmp_path,
    )
    assert out.exists()
    assert calls.get("steps", 0) >= 14
