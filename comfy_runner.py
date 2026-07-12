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
) -> dict[str, Any]:
    """Return a deep-copied workflow with dynamic fields injected."""
    wf = json.loads(json.dumps(workflow))
    nm = node_map or config.NODE_MAP
    seed = seed if seed is not None else random.randint(1, 2_147_483_647)

    if include_motion_in_prompt and motion_prompt:
        positive = f"{visual_prompt}, {motion_prompt}, {config.CINEMATIC_SUFFIX}"
    else:
        positive = f"{visual_prompt}, {config.CINEMATIC_SUFFIX}"

    _set_input(wf, nm.get("positive_prompt"), "text", positive)
    _set_input(wf, nm.get("negative_prompt"), "text", config.NEGATIVE_PROMPT)

    # Flux quality: inject configured sampler steps when present
    steps = getattr(config, "FLUX_STEPS", None)
    if steps and nm.get("ksampler_seed"):
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

    # Start image / character ref (LoadImage)
    if reference_image_name:
        _set_input(wf, nm.get("ipadapter_image"), "image", reference_image_name)

    return wf


def stage_reference_image(src: Path, dest_name: str) -> str:
    """Copy a reference still into ComfyUI input folder; return filename for LoadImage."""
    config.COMFYUI_INPUT.mkdir(parents=True, exist_ok=True)
    dest = config.COMFYUI_INPUT / dest_name
    shutil.copy2(src, dest)
    return dest_name


def run_workflow(
    workflow: dict[str, Any],
    *,
    client_id: str | None = None,
    timeout_s: float = 1800.0,
) -> tuple[str, list[Path]]:
    cid = client_id or new_client_id()
    result = queue_prompt(workflow, client_id=cid)
    prompt_id = result["prompt_id"]
    track_execution(prompt_id, client_id=cid, timeout_s=timeout_s)
    history = get_history(prompt_id)
    entry = history.get(prompt_id) or {}
    paths = collect_output_paths(entry)
    return prompt_id, paths


def pick_best_output(paths: list[Path], prefix: str) -> Path | None:
    videos = [p for p in paths if p.suffix.lower() in {".mp4", ".webm", ".gif", ".mkv"}]
    images = [p for p in paths if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    if videos:
        return videos[0]
    if images:
        return images[0]
    fallback = latest_files_with_prefix(prefix)
    return fallback[0] if fallback else None
