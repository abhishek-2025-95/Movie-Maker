import subprocess
from pathlib import Path

import config
import editor


def test_ffmpeg_upscale_hq_chain_uses_eq_unsharp_noise(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "EXPORT_UPSCALE_HQ_CHAIN", True)
    monkeypatch.setattr(config, "EXPORT_UPSCALE_UNSHARP", False)
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(editor, "_ffmpeg_bin", lambda: "ffmpeg")

    src = tmp_path / "draft.mp4"
    dest = tmp_path / "out.mp4"
    src.write_bytes(b"fake")

    editor._ffmpeg_upscale(src, dest, 1920, 1080)

    cmd = captured["cmd"]
    vf_idx = cmd.index("-vf")
    vf = cmd[vf_idx + 1]
    assert "scale=1920:1080:flags=lanczos" in vf
    assert "eq=" in vf
    assert "unsharp=" in vf
    assert "noise=" in vf
    assert "-c:a" in cmd
    assert "aac" in cmd
