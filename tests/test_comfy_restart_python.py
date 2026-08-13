"""Comfy relaunch must prefer the live/portable interpreter, not system Python311."""
from pathlib import Path

import config
from utils import comfy_python_candidates, resolve_comfy_python


def test_candidates_prefer_embeded_over_system(tmp_path, monkeypatch):
    root = tmp_path / "ComfyUI"
    root.mkdir()
    (root / "main.py").write_text("x", encoding="utf-8")
    embed = root / "python_embeded"
    embed.mkdir()
    py = embed / "python.exe"
    py.write_bytes(b"fake")
    system = tmp_path / "Python311" / "python.exe"
    system.parent.mkdir()
    system.write_bytes(b"sys")
    monkeypatch.setattr(config, "COMFYUI_MAIN", root / "main.py")
    monkeypatch.setattr(config, "COMFYUI_PYTHON", system)
    got = resolve_comfy_python()
    assert got == py


def test_candidates_prefer_running_exe(tmp_path, monkeypatch):
    live = tmp_path / "live" / "python.exe"
    live.parent.mkdir()
    live.write_bytes(b"live")
    monkeypatch.setattr(config, "COMFYUI_MAIN", tmp_path / "ComfyUI" / "main.py")
    monkeypatch.setattr(config, "COMFYUI_PYTHON", tmp_path / "missing.exe")
    cands = comfy_python_candidates(running_exe=live)
    assert cands[0] == live
    assert resolve_comfy_python(running_exe=live) == live


def test_resolve_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "COMFYUI_MAIN", tmp_path / "nope" / "main.py")
    monkeypatch.setattr(config, "COMFYUI_PYTHON", tmp_path / "missing.exe")
    assert resolve_comfy_python() is None
