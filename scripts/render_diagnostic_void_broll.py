"""Best-fit B-roll for sterile diagnostic void: procedural faint pulsing grid.

Pitch-black #000, micro grid breathe only, 9:16 @ 1080x1920, 10s, no text.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "final_outputs" / "diagnostic_void_9x16_10s.mp4"
W, H = 1080, 1920
FPS = 24
DURATION = 10.0
# Grid: barely visible dark-grey on pure black
GRID_BASE = 18  # 0–255 grey
GRID_PULSE = 10  # amplitude
GRID_STEP = 48  # px between lines
LINE_W = 1


def make_frame(t: float) -> np.ndarray:
    # Slow atmospheric breathe (~0.35 Hz)
    pulse = 0.5 + 0.5 * np.sin(2.0 * np.pi * 0.35 * t)
    g = int(np.clip(GRID_BASE + GRID_PULSE * pulse, 0, 40))
    frame = np.zeros((H, W, 3), dtype=np.uint8)
    # Vertical + horizontal faint diagnostic lattice
    frame[:, ::GRID_STEP, :] = g
    frame[::GRID_STEP, :, :] = g
    # Slightly stronger every 4th line (clinical HUD feel, still dim)
    frame[:, :: GRID_STEP * 4, :] = min(g + 6, 48)
    frame[:: GRID_STEP * 4, :, :] = min(g + 6, 48)
    # Soft center vignette haze (near-invisible)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cy, cx = (H - 1) / 2.0, (W - 1) / 2.0
    dist = np.sqrt(((yy - cy) / cy) ** 2 + ((xx - cx) / cx) ** 2)
    haze = (np.clip(1.0 - dist, 0, 1) ** 2) * (3.0 + 2.0 * pulse)
    frame = np.clip(frame.astype(np.float32) + haze[..., None], 0, 255).astype(np.uint8)
    return frame


def main() -> None:
    from moviepy.editor import VideoClip

    OUT.parent.mkdir(parents=True, exist_ok=True)
    clip = VideoClip(make_frame, duration=DURATION).set_fps(FPS)
    clip.write_videofile(
        str(OUT),
        fps=FPS,
        codec="libx264",
        audio=False,
        bitrate="8000k",
        preset="medium",
        ffmpeg_params=["-pix_fmt", "yuv420p"],
        logger=None,
    )
    clip.close()
    print(f"DONE {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
