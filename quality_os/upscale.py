"""Generative upscale via Real-ESRGAN (spandrel) with HQ ffmpeg fallback."""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

import config

log = logging.getLogger(__name__)

ESR_PATH = Path(r"C:\ComfyUI\models\upscale_models\RealESRGAN_x2plus.pth")


def realesrgan_available() -> bool:
    if not ESR_PATH.is_file() or ESR_PATH.stat().st_size < 50 * 1024 * 1024:
        return False
    try:
        import spandrel  # noqa: F401
        import torch  # noqa: F401
        from PIL import Image  # noqa: F401

        return True
    except ImportError:
        return False


def _load_model():
    import torch
    from spandrel import ModelLoader

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ModelLoader().load_from_file(str(ESR_PATH))
    model = model.eval().to(device)
    return model, device


def upscale_image_file(src: Path, dest: Path) -> Path:
    """Upscale a single image with RealESRGAN_x2plus."""
    import numpy as np
    import torch
    from PIL import Image

    model, device = _load_model()
    img = Image.open(src).convert("RGB")
    arr = np.array(img).astype("float32") / 255.0
    t = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(device)
    with torch.inference_mode():
        out = model(t)
    out = out.clamp(0, 1).squeeze(0).permute(1, 2, 0).cpu().numpy()
    Image.fromarray((out * 255).astype("uint8")).save(dest)
    return dest


def upscale_video_to_master(
    src: Path,
    dest: Path,
    *,
    out_w: int,
    out_h: int,
) -> Path:
    """Real-ESRGAN frames → scale to master size → H.264. Falls back to HQ ffmpeg chain."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not (getattr(config, "EXPORT_USE_REALESRGAN", True) and realesrgan_available()):
        return _hq_ffmpeg(src, dest, out_w, out_h)

    log.info("Real-ESRGAN upscale %s → %sx%s", src.name, out_w, out_h)
    with tempfile.TemporaryDirectory(prefix="dx_esr_") as td:
        tdir = Path(td)
        frames_in = tdir / "in"
        frames_out = tdir / "out"
        frames_in.mkdir()
        frames_out.mkdir()
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-vsync", "0", str(frames_in / "f_%06d.png")],
            check=True,
            capture_output=True,
        )
        pngs = sorted(frames_in.glob("f_*.png"))
        if not pngs:
            log.warning("No frames extracted; HQ ffmpeg fallback")
            return _hq_ffmpeg(src, dest, out_w, out_h)
        for i, p in enumerate(pngs):
            up = frames_out / p.name
            upscale_image_file(p, up)
            if (i + 1) % 24 == 0:
                log.info("Real-ESRGAN frame %s/%s", i + 1, len(pngs))
        # scale exact master + encode
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                str(getattr(config, "FPS", 24)),
                "-i",
                str(frames_out / "f_%06d.png"),
                "-i",
                str(src),
                "-map",
                "0:v",
                "-map",
                "1:a?",
                "-vf",
                f"scale={out_w}:{out_h}:flags=lanczos",
                "-c:v",
                "libx264",
                "-preset",
                getattr(config, "EXPORT_PRESET", "slow"),
                "-b:v",
                getattr(config, "EXPORT_BITRATE", "15000k"),
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(dest),
            ],
            check=True,
            capture_output=True,
        )
    return dest


def _hq_ffmpeg(src: Path, dest: Path, out_w: int, out_h: int) -> Path:
    vf = (
        f"scale={out_w}:{out_h}:flags=lanczos,"
        f"eq=contrast=1.08:brightness=-0.02:saturation=0.92:gamma=0.95,"
        f"unsharp=3:3:0.55:3:3:0.0,"
        f"noise=alls=6:allf=t"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        getattr(config, "EXPORT_PRESET", "slow"),
        "-b:v",
        getattr(config, "EXPORT_BITRATE", "15000k"),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(dest),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return dest
    except subprocess.CalledProcessError:
        # silent video may lack audio
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            getattr(config, "EXPORT_PRESET", "slow"),
            "-b:v",
            getattr(config, "EXPORT_BITRATE", "15000k"),
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return dest
