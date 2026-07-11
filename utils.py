"""ComfyUI HTTP + WebSocket helpers."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import websocket

import config


def new_client_id() -> str:
    return str(uuid.uuid4())


def http_get_json(url: str, timeout: float = 30.0) -> Any:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def queue_prompt(
    prompt_workflow: dict,
    server_address: str | None = None,
    client_id: str | None = None,
) -> dict:
    server = server_address or config.COMFYUI_HOST
    cid = client_id or new_client_id()
    payload = {"prompt": prompt_workflow, "client_id": cid}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://{server}/prompt",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def track_execution(
    prompt_id: str,
    server_address: str | None = None,
    client_id: str | None = None,
    timeout_s: float = 1800.0,
) -> None:
    """Block until ComfyUI finishes the given prompt_id."""
    import time

    server = server_address or config.COMFYUI_HOST
    cid = client_id or new_client_id()
    ws = websocket.WebSocket()
    ws.settimeout(30)
    ws.connect(f"ws://{server}/ws?clientId={cid}")
    start = time.time()
    try:
        while True:
            if time.time() - start > timeout_s:
                raise TimeoutError(f"ComfyUI job {prompt_id} timed out after {timeout_s}s")
            try:
                out = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not isinstance(out, str):
                continue
            message = json.loads(out)
            if message.get("type") != "executing":
                continue
            data = message.get("data") or {}
            if data.get("prompt_id") == prompt_id and data.get("node") is None:
                return
    finally:
        ws.close()


def get_history(prompt_id: str, server_address: str | None = None) -> dict:
    server = server_address or config.COMFYUI_HOST
    return http_get_json(f"http://{server}/history/{prompt_id}")


def comfyui_reachable(server_address: str | None = None) -> bool:
    server = server_address or config.COMFYUI_HOST
    try:
        http_get_json(f"http://{server}/system_stats", timeout=5)
        return True
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        try:
            http_get_json(f"http://{server}/object_info", timeout=5)
            return True
        except Exception:
            return False


def collect_output_paths(history_entry: dict, output_root: Path | None = None) -> list[Path]:
    """Extract saved file paths from a ComfyUI history item."""
    root = output_root or config.COMFYUI_OUTPUT
    outputs = history_entry.get("outputs") or {}
    paths: list[Path] = []
    for node_out in outputs.values():
        for key in ("images", "gifs", "videos"):
            for item in node_out.get(key) or []:
                filename = item.get("filename")
                if not filename:
                    continue
                subfolder = item.get("subfolder") or ""
                paths.append(root / subfolder / filename if subfolder else root / filename)
    return paths


def latest_files_with_prefix(prefix: str, output_root: Path | None = None) -> list[Path]:
    root = output_root or config.COMFYUI_OUTPUT
    if not root.exists():
        return []
    matches = sorted(root.glob(f"{prefix}*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches
