"""Concept still-QC: blank reject + porch-lantern hotspot."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from still_qc import has_warm_hotspot, hero_passes_concept_qc, is_unusable_still


def test_gray_still_is_unusable(tmp_path):
    p = tmp_path / "gray.png"
    Image.new("RGB", (256, 256), (128, 128, 128)).save(p)
    assert is_unusable_still(p) is True
    assert hero_passes_concept_qc(p) is False


def _textured_rgb(w: int, h: int, base: tuple[int, int, int]) -> Image.Image:
    im = Image.new("RGB", (w, h))
    px = im.load()
    br, bg, bb = base
    for y in range(h):
        for x in range(w):
            n = (x * 37 + y * 53) % 80
            px[x, y] = (
                min(255, br + (x // 2) % 90 + n),
                min(255, bg + (y // 3) % 70 + (n // 2)),
                min(255, bb + ((x + y) // 4) % 50 + (n // 3)),
            )
    return im


def test_lantern_hotspot_upper_right(tmp_path):
    dusk = _textured_rgb(192, 192, (20, 24, 50))
    draw = ImageDraw.Draw(dusk)
    draw.ellipse((140, 18, 178, 56), fill=(255, 210, 90))
    p = tmp_path / "lamp.png"
    dusk.save(p)
    assert is_unusable_still(p) is False
    assert has_warm_hotspot(p) is True
    assert hero_passes_concept_qc(p) is True


def test_even_warm_scene_without_lamp_fails_hotspot(tmp_path):
    p = tmp_path / "flat.png"
    # Brighter on the LEFT so upper-right is not a lamp stand-in.
    im = _textured_rgb(192, 192, (70, 50, 30))
    px = im.load()
    for y in range(192):
        for x in range(80):
            r, g, b = px[x, y]
            px[x, y] = (min(255, r + 40), min(255, g + 20), b)
    im.save(p)
    assert is_unusable_still(p) is False
    assert has_warm_hotspot(p) is False
    assert hero_passes_concept_qc(p) is False
