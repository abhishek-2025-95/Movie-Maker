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

    # Wan native graph is happier at moderate res; keep Flux higher then downscale for I2V.
    width, height = config.RATIO_SIZES[job.ratio]
    wan_w, wan_h = (640, 1136) if job.ratio == "9:16" else (1136, 640)
    clip_paths: list[Path] = []
    narr_paths: list[Path] = []
    captions: list[str] = []
    character_ref: str | None = None

    flux_template = None
    wan_template = None
    single_template = None
    use_two_stage = False
    if not dry_run:
        use_two_stage = bool(
            config.TWO_STAGE and config.WORKFLOW_FLUX.exists() and config.WORKFLOW_WAN.exists()
        )
        try:
            if use_two_stage:
                flux_template = load_workflow(config.WORKFLOW_FLUX)
                wan_template = load_workflow(config.WORKFLOW_WAN)
                log.info("Two-stage mode: Flux still → Wan 2.2 I2V")
            else:
                single_template = load_workflow()
                log.info("Single-workflow mode: %s", config.WORKFLOW_API.name)
        except WorkflowNotFoundError as exc:
            _log_error(str(exc))
            return None

    for idx, scene in enumerate(screenplay.scenes):
        prefix = f"dx_{slug}_s{idx:02d}"
        log.info("Scene %s/%s", idx + 1, len(screenplay.scenes))

        vo_path = work / f"narration_{idx:02d}.wav"
        try:
            synthesize(scene.narration, lang=job.lang, out_path=vo_path)
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
            placeholder = work / f"{prefix}.mp4"
            _write_placeholder_clip(placeholder, width, height, config.SECONDS_PER_SCENE)
            clip_paths.append(placeholder)
            continue

        try:
            if use_two_stage:
                assert flux_template is not None and wan_template is not None
                # Stage A — Flux still (character mode reuses first-scene look via prompt identity)
                flux_prompt = scene.visual_prompt
                if job.mode == "character" and character_ref:
                    flux_prompt = (
                        f"{scene.visual_prompt}, same character identity and wardrobe as reference"
                    )
                flux_wf = apply_scene_to_workflow(
                    flux_template,
                    visual_prompt=flux_prompt,
                    motion_prompt="",
                    filename_prefix=f"{prefix}_still",
                    width=width,
                    height=height,
                    node_map=config.NODE_MAP_FLUX,
                    include_motion_in_prompt=False,
                )
                _pid, flux_outs = run_workflow(flux_wf, client_id=cid)
                still = pick_best_output(flux_outs, f"{prefix}_still")
                if not still:
                    _log_error(f"No Flux still for {prefix}")
                    continue
                still_local = work / still.name
                shutil.copy2(still, still_local)
                start_name = stage_reference_image(still_local, f"{prefix}_start.png")
                if job.mode == "character" and idx == 0:
                    character_ref = stage_reference_image(still_local, f"ref_{slug}.png")

                # Stage B — Wan I2V from that still
                wan_wf = apply_scene_to_workflow(
                    wan_template,
                    visual_prompt=scene.visual_prompt,
                    motion_prompt=scene.motion_prompt,
                    filename_prefix=prefix,
                    width=wan_w,
                    height=wan_h,
                    reference_image_name=start_name,
                    node_map=config.NODE_MAP_WAN,
                )
                _pid2, wan_outs = run_workflow(wan_wf, client_id=cid)
                best = pick_best_output(wan_outs, prefix)
            else:
                assert single_template is not None
                wf = apply_scene_to_workflow(
                    single_template,
                    visual_prompt=scene.visual_prompt,
                    motion_prompt=scene.motion_prompt,
                    filename_prefix=prefix,
                    width=width,
                    height=height,
                    reference_image_name=character_ref if job.mode == "character" else None,
                    node_map=config.NODE_MAP,
                )
                _pid, outs = run_workflow(wf, client_id=cid)
                best = pick_best_output(outs, prefix)
                if best and job.mode == "character" and idx == 0:
                    if best.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                        character_ref = stage_reference_image(best, f"ref_{slug}.png")
                    else:
                        ref_still = work / f"ref_{slug}.png"
                        if _extract_frame(best, ref_still):
                            character_ref = stage_reference_image(ref_still, f"ref_{slug}.png")

            if not best:
                _log_error(f"No ComfyUI output for {prefix}")
                continue
            local = work / best.name
            shutil.copy2(best, local)
            clip_paths.append(local)
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
