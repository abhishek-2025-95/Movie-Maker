import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import config
import editor


class _MockClip:
    def __init__(self, duration: float, *, frame=None):
        self.duration = duration
        self.fps = 24
        self._frame = frame if frame is not None else [[0, 0, 0]]

    def subclip(self, start, end):
        out = _MockClip(end - start, frame=self._frame)
        out.fps = self.fps
        return out

    def get_frame(self, t):
        return self._frame


def test_fit_clip_to_duration_no_freeze_pad_when_disabled(monkeypatch):
    monkeypatch.setattr(config, "QUALITY_ALLOW_FREEZE_PAD", False)
    clip = _MockClip(2.0)

    image_clip = MagicMock()
    concat = MagicMock()
    monkeypatch.setattr("moviepy.editor.ImageClip", image_clip)
    monkeypatch.setattr("moviepy.editor.concatenate_videoclips", concat)

    result = editor._fit_clip_to_duration(clip, 5.0)

    assert result is clip
    assert result.duration == 2.0
    image_clip.assert_not_called()
    concat.assert_not_called()


def test_fit_clip_to_duration_still_trims_when_disabled(monkeypatch):
    monkeypatch.setattr(config, "QUALITY_ALLOW_FREEZE_PAD", False)
    clip = _MockClip(6.0)

    result = editor._fit_clip_to_duration(clip, 5.0)

    assert result.duration == 5.0


def test_fit_clip_to_duration_freeze_pad_when_enabled(monkeypatch):
    monkeypatch.setattr(config, "QUALITY_ALLOW_FREEZE_PAD", True)
    clip = _MockClip(2.0)
    clip.get_frame = MagicMock(return_value=[[0, 0, 0]])

    freeze = MagicMock()
    freeze.set_duration.return_value = freeze
    freeze.set_fps.return_value = freeze

    image_clip = MagicMock(return_value=freeze)
    concat = MagicMock(return_value=_MockClip(5.0))
    monkeypatch.setattr("moviepy.editor.ImageClip", image_clip)
    monkeypatch.setattr("moviepy.editor.concatenate_videoclips", concat)

    result = editor._fit_clip_to_duration(clip, 5.0)

    image_clip.assert_called_once()
    concat.assert_called_once()
    assert result.duration == 5.0


def test_ffmpeg_fit_duration_no_tpad_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "QUALITY_ALLOW_FREEZE_PAD", False)
    monkeypatch.setattr(editor, "_ffprobe_duration", lambda _src: 2.0)
    monkeypatch.setattr(editor, "_ffmpeg_bin", lambda: "ffmpeg")

    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        dest = Path(cmd[-1])
        dest.write_bytes(b"ok")

    monkeypatch.setattr(subprocess, "run", fake_run)

    src = tmp_path / "in.mp4"
    dest = tmp_path / "out.mp4"
    src.write_bytes(b"fake")

    editor._ffmpeg_fit_duration(src, dest, 5.0)

    cmd = captured["cmd"]
    vf = " ".join(cmd)
    assert "tpad" not in vf


def test_ffmpeg_fit_duration_still_trims_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "QUALITY_ALLOW_FREEZE_PAD", False)
    monkeypatch.setattr(editor, "_ffprobe_duration", lambda _src: 6.0)
    monkeypatch.setattr(editor, "_ffmpeg_bin", lambda: "ffmpeg")

    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        dest = Path(cmd[-1])
        dest.write_bytes(b"ok")

    monkeypatch.setattr(subprocess, "run", fake_run)

    src = tmp_path / "in.mp4"
    dest = tmp_path / "out.mp4"
    src.write_bytes(b"fake")

    editor._ffmpeg_fit_duration(src, dest, 5.0)

    cmd = captured["cmd"]
    assert "-t" in cmd
    assert "5.0000" in cmd
    assert "tpad" not in " ".join(cmd)
