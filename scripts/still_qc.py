#!/usr/bin/env python3
"""Detect near-solid / gray / blank stills (Flux VAE failure signature)."""
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


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("still.png")
    bad = is_unusable_still(target)
    print("UNUSABLE" if bad else "OK", target)
    raise SystemExit(1 if bad else 0)
