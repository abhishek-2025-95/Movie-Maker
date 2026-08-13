"""start_comfyui finds main.py even when portable bats are missing."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config
import start_comfyui as sc


def test_find_main_uses_configured_path(tmp_path, monkeypatch):
    main = tmp_path / "ComfyUI" / "main.py"
    main.parent.mkdir()
    main.write_text("# comfy", encoding="utf-8")
    monkeypatch.setattr(config, "COMFYUI_MAIN", main)
    monkeypatch.setattr(config, "COMFYUI_ROOT", main.parent)
    monkeypatch.setattr(sc, "_extra_roots", lambda: [main.parent])
    assert sc.find_main() == main


def test_find_main_none(tmp_path, monkeypatch):
    missing = tmp_path / "nope" / "main.py"
    monkeypatch.setattr(config, "COMFYUI_MAIN", missing)
    monkeypatch.setattr(config, "COMFYUI_ROOT", missing.parent)
    monkeypatch.setattr(sc, "_extra_roots", lambda: [missing.parent])
    assert sc.find_main() is None


def test_repair_huggingface_hub_uses_required_spec(monkeypatch):
    calls: list[list[str]] = []

    def fake_call(cmd, **kwargs):
        calls.append(list(cmd))
        return 0

    monkeypatch.setattr(sc.subprocess, "call", fake_call)
    py = Path(r"C:\Python311\python.exe")
    assert sc.repair_huggingface_hub(py) == 0
    assert calls and "huggingface-hub>=1.5.0,<2.0" in calls[0]
    assert calls[0][:3] == [str(py), "-m", "pip"]
    assert sc.HF_HUB_SPEC == "huggingface-hub>=1.5.0,<2.0"
