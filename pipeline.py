"""End-to-end topic → cinematic MP4 pipeline."""
from __future__ import annotations

import logging
import shutil
import traceback
from pathlib import Path

from PIL import Image

if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS  # type: ignore[attr-defined]

import config
from comfy_runner import (
    WorkflowNotFoundError,
    apply_scene_to_workflow,
    load_workflow,
    pick_best_output,
    run_workflow,
    stage_reference_image,
)
from director import Screenplay, TopicJob, generate_screenplay
from editor import assemble_video
from utils import new_client_id
from voice import synthesize

log = logging.getLogger(__name__)


def _log_error(msg: str) -> None:
    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    with config.ERROR_LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")
    log.error(msg)


def _slug(text: str, limit: int = 40) -> str:
    keep = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text.strip())
    return keep[:limit].strip("_") or "video"


def run_topic(job: TopicJob, *, dry_run: bool = False, client_id: str | None = None) -> Path | None:
    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cid = client_id or new_client_id()
    slug = _slug(job.topic)
    work = config.TEMP_DIR / slug
    work.mkdir(parents=True, exist_ok=True)

    log.info("Director scripting: %s [%s/%s/%s]", job.topic, job.mode, job.ratio, job.lang)
    if dry_run:
        screenplay = Screenplay(
            title=job.topic,
            scenes=[],
        )
        # Minimal fake scenes for dry-run assembly skip
        from director import Scene

        screenplay.scenes = [
            Scene(
                narration=f"Dry run narration for {job.topic}, scene {i+1}.",
                visual_prompt=f"cinematic still about {job.topic}, scene {i+1}",
                motion_prompt="slow cinematic push-in",
            )
            for i in range(2)
        ]
    else:
        screenplay = generate_screenplay(job)

    if not screenplay.scenes:
        _log_error(f"No scenes generated for topic: {job.topic}")
        return None

    # Save screenplay for debugging
    (work / "screenplay.json").write_text(
        __import__("json").dumps(screenplay.raw or {
            "title": screenplay.title,
            "scenes": [s.__dict__ for s in screenplay.scenes],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    width, height = config.RATIO_SIZES[job.ratio]
    clip_paths: list[Path] = []
    narr_paths: list[Path] = []
    captions: list[str] = []
    reference_name: str | None = None

    workflow_template = None
    if not dry_run:
        try:
            workflow_template = load_workflow()
        except WorkflowNotFoundError as exc:
            _log_error(str(exc))
            return None

    for idx, scene in enumerate(screenplay.scenes):
        prefix = f"dx_{slug}_s{idx:02d}"
        log.info("Scene %s/%s", idx + 1, len(screenplay.scenes))

        # Voice first (can overlap conceptually; sequential for VRAM safety)
        vo_path = work / f"narration_{idx:02d}.wav"
        try:
            synthesize(scene.narration, lang=job.lang, out_path=vo_path)
            # edge fallback may write .mp3
            if not vo_path.exists():
                alt = vo_path.with_suffix(".mp3")
                if alt.exists():
                    vo_path = alt
            narr_paths.append(vo_path)
        except Exception as exc:  # noqa: BLE001
            _log_error(f"Voice failed scene {idx}: {exc}")
            narr_paths.append(vo_path)

        captions.append(scene.narration)

        if dry_run:
            # Create a placeholder colored clip via moviepy
            placeholder = work / f"{prefix}.mp4"
            _write_placeholder_clip(placeholder, width, height, config.SECONDS_PER_SCENE)
            clip_paths.append(placeholder)
            continue

        assert workflow_template is not None
        wf = apply_scene_to_workflow(
            workflow_template,
            visual_prompt=scene.visual_prompt,
            motion_prompt=scene.motion_prompt,
            filename_prefix=prefix,
            width=width,
            height=height,
            reference_image_name=reference_name if job.mode == "character" else None,
        )
        try:
            _prompt_id, outs = run_workflow(wf, client_id=cid)
            best = pick_best_output(outs, prefix)
            if not best:
                _log_error(f"No ComfyUI output for {prefix}")
                continue
            local = work / best.name
            shutil.copy2(best, local)
            clip_paths.append(local)

            # Lock character from first still/frame if possible
            if job.mode == "character" and idx == 0:
                if local.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    reference_name = stage_reference_image(local, f"ref_{slug}.png")
                else:
                    # Extract first frame from video as reference
                    ref_still = work / f"ref_{slug}.png"
                    if _extract_frame(local, ref_still):
                        reference_name = stage_reference_image(ref_still, f"ref_{slug}.png")
        except Exception as exc:  # noqa: BLE001
            _log_error(f"ComfyUI scene {idx} failed: {exc}\n{traceback.format_exc()}")
            continue

    if not clip_paths:
        _log_error(f"No clips produced for: {job.topic}")
        return None

    out_file = config.OUTPUT_DIR / f"{slug}.mp4"
    try:
        assemble_video(
            clip_paths,
            narr_paths,
            out_path=out_file,
            ratio=job.ratio,
            burn_captions=True,
            caption_lines=captions,
        )
        log.info("Wrote %s", out_file)
        return out_file
    except Exception as exc:  # noqa: BLE001
        _log_error(f"Assembly failed for {job.topic}: {exc}\n{traceback.format_exc()}")
        return None


def _write_placeholder_clip(path: Path, w: int, h: int, seconds: float) -> None:
    import numpy as np
    from moviepy.editor import ImageClip

    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = (24, 28, 40)
    clip = ImageClip(frame).set_duration(seconds)
    clip.write_videofile(str(path), fps=config.FPS, codec="libx264", audio=False, verbose=False, logger=None)
    clip.close()


def _extract_frame(video_path: Path, out_png: Path) -> bool:
    try:
        from moviepy.editor import VideoFileClip

        clip = VideoFileClip(str(video_path))
        clip.save_frame(str(out_png), t=min(0.1, max(clip.duration / 2, 0)))
        clip.close()
        return out_png.exists()
    except Exception:  # noqa: BLE001
        return False
