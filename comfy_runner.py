"""Inject prompts into ComfyUI workflow_api.json and run jobs."""
from __future__ import annotations

import json
import random
import shutil
from pathlib import Path
from typing import Any

import config
from utils import (
    collect_output_paths,
    get_history,
    latest_files_with_prefix,
    new_client_id,
    queue_prompt,
    track_execution,
)


class WorkflowNotFoundError(FileNotFoundError):
    pass


def load_workflow(path: Path | None = None) -> dict[str, Any]:
    path = path or config.WORKFLOW_API
    if not path.exists():
        example = config.WORKFLOW_EXAMPLE
        raise WorkflowNotFoundError(
            f"Missing {path}. Export ComfyUI Dev Mode → Save (API Format) "
            f"as workflow_api.json (see {example})."
        )
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _set_input(workflow: dict, node_id: str | None, key: str, value: Any) -> bool:
    if not node_id or node_id not in workflow:
        return False
    node = workflow[node_id]
    inputs = node.setdefault("inputs", {})
    inputs[key] = value
    return True


def _set_all_seeds(workflow: dict[str, Any], seed: int) -> None:
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") not in {"KSampler", "KSamplerAdvanced", "RandomNoise"}:
            continue
        inputs = node.setdefault("inputs", {})
        if "seed" in inputs:
            inputs["seed"] = seed
        if "noise_seed" in inputs:
            inputs["noise_seed"] = seed


def apply_scene_to_workflow(
    workflow: dict[str, Any],
    *,
    visual_prompt: str,
    motion_prompt: str = "",
    filename_prefix: str,
    seed: int | None = None,
    width: int | None = None,
    height: int | None = None,
    reference_image_name: str | None = None,
    node_map: dict | None = None,
    include_motion_in_prompt: bool = True,
    cinematic_suffix: str | None = None,
    negative_prompt: str | None = None,
) -> dict[str, Any]:
    """Return a deep-copied workflow with dynamic fields injected."""
    wf = json.loads(json.dumps(workflow))
    nm = node_map or config.NODE_MAP
    seed = seed if seed is not None else random.randint(1, 2_147_483_647)
    suffix = cinematic_suffix or config.CINEMATIC_SUFFIX
    negative = negative_prompt or getattr(config, "FLUX_NEGATIVE_PROMPT", None) or config.NEGATIVE_PROMPT
    # Always enforce hardcoded Flux anatomy/text guardrails
    hard = getattr(config, "FLUX_NEGATIVE_PROMPT", "")
    if hard and hard not in negative:
        negative = hard

    if include_motion_in_prompt and motion_prompt:
        positive = f"{visual_prompt}, {motion_prompt}, {suffix}"
    else:
        positive = f"{visual_prompt}, {suffix}"

    _set_input(wf, nm.get("positive_prompt"), "text", positive)
    _set_input(wf, nm.get("negative_prompt"), "text", negative)

    # Still-stage only: never overwrite Wan high/low sampler step counts
    steps = getattr(config, "FLUX_STEPS", None)
    still_graph = any(
        isinstance(n, dict) and n.get("class_type") == "SaveImage" for n in wf.values()
    )
    if steps and still_graph and nm.get("ksampler_seed"):
        _set_input(wf, nm.get("ksampler_seed"), "steps", int(steps))

    _set_all_seeds(wf, seed)
    # Also honor mapped sampler if present
    for seed_key in ("seed", "noise_seed"):
        _set_input(wf, nm.get("ksampler_seed"), seed_key, seed)

    for prefix_key in ("filename_prefix", "filename"):
        if _set_input(wf, nm.get("save_prefix"), prefix_key, filename_prefix):
            break

    if width is not None:
        _set_input(wf, nm.get("width"), "width", width)
    if height is not None:
        _set_input(wf, nm.get("height"), "height", height)
    # Keep ModelSamplingFlux shift math in sync with latent size
    for node in wf.values():
        if node.get("class_type") == "ModelSamplingFlux":
            if width is not None:
                node.setdefault("inputs", {})["width"] = width
            if height is not None:
                node.setdefault("inputs", {})["height"] = height

    # Start image / character ref (LoadImage)
    if reference_image_name:
        _set_input(wf, nm.get("ipadapter_image"), "image", reference_image_name)

    return wf


def stage_reference_image(src: Path, dest_name: str) -> str:
    """Copy a reference still into ComfyUI input folder; return filename for LoadImage.

    Resizes to the active Wan canvas when possible so I2V latents match the start frame.
    """
    config.COMFYUI_INPUT.mkdir(parents=True, exist_ok=True)
    dest = config.COMFYUI_INPUT / dest_name
    try:
        from PIL import Image

        with Image.open(src) as im:
            rgb = im.convert("RGB")
            # Prefer configured Wan size for 9:16; fall back to copy as-is
            target = None
            for key in ("9:16", "16:9"):
                sizes = getattr(config, "WAN_SIZES", {})
                if key in sizes:
                    # Infer from source aspect
                    w, h = sizes[key]
                    if (rgb.width >= rgb.height and w >= h) or (rgb.width < rgb.height and w < h):
                        target = (w, h)
                        break
            if target is None:
                target = config.WAN_SIZES.get("9:16", (rgb.width, rgb.height))
            if rgb.size != target:
                rgb = rgb.resize(target, Image.Resampling.LANCZOS)
            rgb.save(dest, format="PNG")
    except Exception:
        shutil.copy2(src, dest)
    return dest_name


def run_workflow(
    workflow: dict[str, Any],
    *,
    client_id: str | None = None,
    timeout_s: float | None = None,
) -> tuple[str, list[Path]]:
    cid = client_id or new_client_id()
    if timeout_s is None:
        timeout_s = float(getattr(config, "COMFY_JOB_TIMEOUT_S", 3600.0))
    result = queue_prompt(workflow, client_id=cid)
    prompt_id = result["prompt_id"]
    track_execution(prompt_id, client_id=cid, timeout_s=timeout_s)
    history = get_history(prompt_id)
    entry = history.get(prompt_id) or {}
    status = entry.get("status") or {}
    if status.get("status_str") == "error" or status.get("completed") is False:
        err_msg = "ComfyUI execution_error"
        for msg in status.get("messages") or []:
            if isinstance(msg, (list, tuple)) and len(msg) >= 2 and msg[0] == "execution_error":
                detail = msg[1] if isinstance(msg[1], dict) else {}
                err_msg = (
                    f"ComfyUI {detail.get('node_type', '?')} "
                    f"[{detail.get('node_id', '?')}]: "
                    f"{detail.get('exception_type', 'Error')}: "
                    f"{detail.get('exception_message', detail)}"
                )
                break
        log = __import__("logging").getLogger(__name__)
        log.error("%s (prompt_id=%s)", err_msg, prompt_id)
    paths = collect_output_paths(entry)
    return prompt_id, paths


def pick_best_output(
    paths: list[Path],
    prefix: str,
    *,
    allow_stale_disk: bool = True,
) -> Path | None:
    videos = [p for p in paths if p.suffix.lower() in {".mp4", ".webm", ".gif", ".mkv"}]
    images = [p for p in paths if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    if videos:
        return videos[0]
    # Motion stage must never fall back to a Flux still PNG
    if "_still" not in prefix and images:
        return None
    if images:
        return images[0]
    if not allow_stale_disk:
        return None
    fallback = [
        p
        for p in latest_files_with_prefix(prefix)
        if "_still" not in p.stem.lower() or "_still" in prefix
    ]
    videos_fb = [p for p in fallback if p.suffix.lower() in {".mp4", ".webm", ".gif", ".mkv"}]
    if videos_fb:
        return videos_fb[0]
    if "_still" in prefix:
        images_fb = [p for p in fallback if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
        return images_fb[0] if images_fb else (fallback[0] if fallback else None)
    return None
