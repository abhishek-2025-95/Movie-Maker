#!/usr/bin/env python3
"""Verify Flux.1-dev FP8 checkpoint is present, sized, and SHA-256 correct.

Exit codes:
  0 = verified OK
  1 = missing / wrong size / hash mismatch
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

# Comfy-Org/flux1-dev · flux1-dev-fp8.safetensors
EXPECTED_SHA256 = "8e91b68084b53a7fc44ed2a3756d821e355ac1a7b6fe29be760c1db532f3d88a"
EXPECTED_BYTES = 17246524772  # Comfy-Org LFS size
MIN_BYTES = 15 * 1024**3  # reject tiny / partial files
DEFAULT_PATH = Path(r"C:\ComfyUI\models\checkpoints\flux1-dev-fp8.safetensors")


def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    if not path.is_file():
        print(f"MISSING: {path}")
        return 1
    size = path.stat().st_size
    print(f"path={path}")
    print(f"size={size} ({size / 1024**3:.2f} GiB)")
    if size < MIN_BYTES:
        print("FAIL: file too small (corrupt/partial)")
        return 1
    if size != EXPECTED_BYTES:
        print(f"FAIL: size mismatch expected={EXPECTED_BYTES}")
        return 1
    print("hashing SHA256...")
    digest = sha256_file(path)
    print(f"sha256={digest}")
    if digest != EXPECTED_SHA256:
        print(f"FAIL: expected {EXPECTED_SHA256}")
        return 1
    print("OK: Flux FP8 verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
