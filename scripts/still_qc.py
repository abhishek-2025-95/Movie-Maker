#!/usr/bin/env python3
"""Detect near-solid / gray / blank stills (Flux VAE failure signature).

Also: cheap concept gates (warm lantern hotspot) so a bad hero never reaches Wan.
"""
from __future__ import annotations

from pathlib import Path


def is_unusable_still(path: Path | str, *, max_std: float = 6.0, max_unique_approx: int = 64) -> bool:
    """Return True if image looks like solid gray/black/noise-collapse.

    Uses a downscaled luminance std-dev; Flux gray failures are nearly constant.
    """
    from PIL import Image
    import numpy as np

    p = Path(path)
    if not p.is_file():
        return True
    with Image.open(p) as im:
        rgb = im.convert("RGB")
        # Small proxy for speed
        small = rgb.resize((64, 64))
        arr = np.asarray(small, dtype=np.float32)
    std = float(arr.std())
    if std <= max_std:
        return True
    # Very few unique colors after coarse quantize
    q = (arr.astype(np.uint8) // 16) * 16
    uniq = len({tuple(px) for px in q.reshape(-1, 3)})
    return uniq <= max_unique_approx


def has_warm_hotspot(
    path: Path | str,
    *,
    min_peak: float = 150.0,
    min_delta: float = 22.0,
) -> bool:
    """True if upper-right holds a bright warm lamp-like peak vs the rest of the frame.

    Proxy for The Porch Light spine: yellow lantern in the upper-right, always on.
    Not a face detector — only cheap enough to reject a hero with no key light.
    """
    from PIL import Image
    import numpy as np

    p = Path(path)
    if not p.is_file():
        return False
    with Image.open(p) as im:
        arr = np.asarray(im.convert("RGB").resize((96, 96)), dtype=np.float32)
    warm = arr[:, :, 0] * 0.55 + arr[:, :, 1] * 0.35 + arr[:, :, 2] * 0.10
    ur = warm[:48, 48:]
    rest = np.concatenate([warm[:48, :48].ravel(), warm[48:, :].ravel()])
    peak = float(ur.max())
    rest_med = float(np.median(rest))
    return peak >= min_peak and (peak - rest_med) >= min_delta


def hero_passes_concept_qc(path: Path | str) -> bool:
    """Hero is usable for Wan: not collapsed, and the lantern motif is present."""
    return (not is_unusable_still(path)) and has_warm_hotspot(path)


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("still.png")
    bad = is_unusable_still(target)
    print("UNUSABLE" if bad else "OK", target)
    raise SystemExit(1 if bad else 0)
