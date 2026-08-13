"""ComfyUI HTTP + WebSocket helpers."""
from __future__ import annotations

import json
import time
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


def _history_done(prompt_id: str, server: str) -> bool:
    try:
        hist = http_get_json(f"http://{server}/history/{prompt_id}", timeout=10)
    except Exception:
        return False
    return bool(hist.get(prompt_id))


def _comfy_reachable(server: str) -> bool:
    try:
        with urllib.request.urlopen(f"http://{server}/system_stats", timeout=3) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except Exception:
        return False


def track_execution(
    prompt_id: str,
    server_address: str | None = None,
    client_id: str | None = None,
    timeout_s: float = 1800.0,
) -> None:
    """Block until ComfyUI finishes the given prompt_id.

    Prefers WebSocket events; falls back to HTTP history polling if the
    socket drops (common on long Wan renders / VRAM pressure).
    """
    server = server_address or config.COMFYUI_HOST
    cid = client_id or new_client_id()
    start = time.time()
    dead_hits = 0

    def remaining() -> float:
        return timeout_s - (time.time() - start)

    while remaining() > 0:
        if _history_done(prompt_id, server):
            return
        if not _comfy_reachable(server):
            dead_hits += 1
            # Wan OOM often kills the process silently — fail fast vs 90m timeout.
            if dead_hits >= 4:
                raise RuntimeError(
                    f"ComfyUI died during job {prompt_id} (API unreachable)"
                )
            time.sleep(3)
            continue
        dead_hits = 0

        ws = websocket.WebSocket()
        ws.settimeout(30)
        try:
            ws.connect(f"ws://{server}/ws?clientId={cid}")
            while remaining() > 0:
                if _history_done(prompt_id, server):
                    return
                if not _comfy_reachable(server):
                    break
                try:
                    out = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                except (ConnectionResetError, ConnectionAbortedError, OSError, websocket.WebSocketConnectionClosedException):
                    break
                if not isinstance(out, str):
                    continue
                try:
                    message = json.loads(out)
                except json.JSONDecodeError:
                    continue
                if message.get("type") != "executing":
                    continue
                data = message.get("data") or {}
                if data.get("prompt_id") == prompt_id and data.get("node") is None:
                    return
        except Exception:
            # Server may be restarting / busy — poll history
            time.sleep(2)
            continue
        finally:
            try:
                ws.close()
            except Exception:
                pass

        time.sleep(2)

    raise TimeoutError(f"ComfyUI job {prompt_id} timed out after {timeout_s}s")


def get_history(prompt_id: str, server_address: str | None = None) -> dict:
    server = server_address or config.COMFYUI_HOST
    return http_get_json(f"http://{server}/history/{prompt_id}")


def force_ollama_cpu() -> None:
    """Force Ollama onto CPU so the full 12GB VRAM stays available for Flux/Wan."""
    import logging
    import os

    log = logging.getLogger(__name__)
    os.environ["OLLAMA_NUM_GPU"] = str(int(getattr(config, "OLLAMA_NUM_GPU", 0)))
    # Belt-and-suspenders: also clear any GPU layer count knobs some builds honor
    os.environ.setdefault("OLLAMA_GPU_OVERHEAD", "0")
    log.info("Ollama forced to CPU (OLLAMA_NUM_GPU=%s)", os.environ["OLLAMA_NUM_GPU"])


def unload_ollama_gpu_models() -> None:
    """Unload Ollama models via HTTP (never spawn `ollama` CLI — that restarts the app)."""
    import logging
    import urllib.error
    import urllib.request

    log = logging.getLogger(__name__)
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return  # Ollama not running — ideal for Flux/Wan

    models = []
    if isinstance(data, dict):
        models = data.get("models") or []
    for m in models:
        name = (m.get("name") or m.get("model") or "").strip()
        if not name:
            continue
        payload = json.dumps({"model": name, "keep_alive": 0}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp.read()
            log.info("Unloaded Ollama model from GPU: %s", name)
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to unload Ollama model %s: %s", name, exc)


def python_from_comfy_launch_bats(root: Path) -> list[Path]:
    """Parse run_nvidia_gpu.bat etc. for the real Comfy interpreter."""
    out: list[Path] = []
    if not root.is_dir():
        return out
    bats = list(root.glob("run*.bat")) + list(root.glob("*.bat"))
    for bat in bats:
        try:
            text = bat.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "main.py" not in text.lower() or "python" not in text.lower():
            continue
        for raw in text.replace("'", " ").replace('"', " ").split():
            token = raw.strip().strip("\\")
            token = token.replace("\\", "/")
            if token.startswith("./"):
                token = token[2:]
            if not token.lower().endswith("python.exe"):
                continue
            p = Path(token)
            if not p.is_absolute():
                p = root / token
            out.append(p)
    return out


def python_has_torch(py: Path) -> bool:
    """True if this interpreter can import torch (Comfy's env, not DirectorX .venv)."""
    import subprocess

    try:
        r = subprocess.run(
            [str(py), "-c", "import torch"],
            capture_output=True,
            timeout=25,
            check=False,
        )
    except Exception:
        return False
    return r.returncode == 0


def comfy_python_candidates(*, running_exe: Path | None = None) -> list[Path]:
    """Preferred Pythons to relaunch ComfyUI (portable embed first, then config)."""
    main_py = Path(getattr(config, "COMFYUI_MAIN", r"C:\ComfyUI\main.py"))
    root = main_py.parent
    configured = Path(
        getattr(
            config,
            "COMFYUI_PYTHON",
            r"C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe",
        )
    )
    ordered = [
        running_exe,
        *python_from_comfy_launch_bats(root),
        root / "python_embeded" / "python.exe",
        root / "python_embedded" / "python.exe",
        root.parent / "python_embeded" / "python.exe",
        root / "venv" / "Scripts" / "python.exe",
        root / ".venv" / "Scripts" / "python.exe",
        configured,
    ]
    out: list[Path] = []
    seen: set[str] = set()
    for p in ordered:
        if p is None:
            continue
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(Path(p))
    return out


def running_comfy_python() -> Path | None:
    """If ComfyUI is already running, return that process's python.exe."""
    try:
        import psutil  # type: ignore
    except Exception:
        return None
    for proc in psutil.process_iter(["pid", "cmdline", "exe"]):
        try:
            cmd = " ".join(proc.info.get("cmdline") or [])
        except Exception:
            continue
        if "ComfyUI" not in cmd or "main.py" not in cmd:
            continue
        exe = proc.info.get("exe")
        if exe:
            p = Path(exe)
            if p.is_file():
                return p
    return None


def resolve_comfy_python(*, running_exe: Path | None = None, require_torch: bool = False) -> Path | None:
    import logging

    log = logging.getLogger(__name__)
    for p in comfy_python_candidates(running_exe=running_exe):
        if not p.is_file():
            continue
        if require_torch and not python_has_torch(p):
            log.info("skip Comfy python without torch: %s", p)
            continue
        return p
    return None


def wait_comfy_healthy(*, wait_sec: float, progress: bool = False) -> bool:
    import urllib.request

    host = config.COMFYUI_HOST
    start = time.time()
    deadline = start + max(1.0, float(wait_sec))
    last_print = -10.0
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://{host}/system_stats", timeout=3) as resp:
                if 200 <= getattr(resp, "status", 200) < 300:
                    return True
        except Exception:
            elapsed = time.time() - start
            if progress and elapsed - last_print >= 10:
                print(
                    f"COMFY_WAIT {int(elapsed)}s/{int(wait_sec)}s "
                    f"http://{host}/system_stats",
                    flush=True,
                )
                last_print = elapsed
            time.sleep(2)
    return False


def restart_comfyui(*, wait_sec: float | None = None) -> bool:
    """Kill and relaunch ComfyUI — only reliable VRAM reset on 12GB lowvram."""
    import logging
    import subprocess
    import sys

    log = logging.getLogger(__name__)
    host = config.COMFYUI_HOST
    main_py = Path(getattr(config, "COMFYUI_MAIN", r"C:\ComfyUI\main.py"))
    # Snapshot the live interpreter BEFORE kill — portable Comfy uses python_embeded,
    # not the system Python311 path in config.
    live_py = running_comfy_python()
    py = resolve_comfy_python(running_exe=live_py, require_torch=True)
    if py is None:
        # Last resort: file exists even if torch probe failed (slow/antivirus).
        py = resolve_comfy_python(running_exe=live_py, require_torch=False)
    # Stop existing ComfyUI listeners (force — wedged procs ignore graceful kill).
    try:
        import psutil  # type: ignore

        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmd = " ".join(proc.info.get("cmdline") or [])
            except Exception:
                continue
            if "ComfyUI" in cmd and "main.py" in cmd:
                try:
                    proc.kill()
                except Exception:
                    pass
        time.sleep(3)
    except Exception:
        pass
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                    "Where-Object { $_.CommandLine -match 'ComfyUI\\\\main\\.py' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; "
                    "Start-Sleep -Seconds 2; "
                    "Get-NetTCPConnection -LocalPort 8188 -ErrorAction SilentlyContinue | "
                    "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
                ),
            ],
            check=False,
            capture_output=True,
            timeout=45,
        )
        time.sleep(3)
    except Exception as exc:  # noqa: BLE001
        log.warning("ComfyUI kill fallback failed: %s", exc)

    if py is None or not py.exists() or not main_py.exists():
        log.error("ComfyUI restart paths missing: py=%s main=%s", py, main_py)
        return False

    # Must NOT redirect stdout/stderr to DEVNULL — Comfy tqdm flush hits Errno 22 and dies.
    # Visible new console so a crash is obvious. Direct Popen (not minimized Start-Process).
    launch_args = tuple(
        getattr(config, "COMFY_LAUNCH_ARGS", None)
        or ("--listen", "127.0.0.1", "--port", "8188", "--normalvram")
    )
    cmd = [str(py), str(main_py), *launch_args]
    log.info("ComfyUI relaunch cmd=%s live_was=%s torch=%s", cmd, live_py, python_has_torch(py))
    print(f"COMFY_LAUNCH {' '.join(cmd)}", flush=True)
    popen_kw: dict = {"cwd": str(main_py.parent), "close_fds": False}
    if sys.platform == "win32":
        popen_kw["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    try:
        subprocess.Popen(cmd, **popen_kw)
    except Exception as exc:  # noqa: BLE001
        log.error("ComfyUI relaunch failed: %s", exc)
        return False

    wait = float(wait_sec if wait_sec is not None else getattr(config, "COMFY_RESTART_WAIT_SEC", 90.0))
    if wait_comfy_healthy(wait_sec=wait, progress=True):
        log.info("ComfyUI restarted and healthy at %s", host)
        return True
    log.error("ComfyUI failed to become healthy after restart (python=%s wait=%.0fs)", py, wait)
    return False


def free_comfyui_memory(
    server_address: str | None = None,
    *,
    unload_models: bool = True,
    free_memory: bool = True,
) -> bool:
    """Ask ComfyUI to unload models / free VRAM between sequential stages.

    Equivalent to a torch.cuda.empty_cache() boundary for the ComfyUI process.
    Returns True if /free accepted the request.
    """
    import gc
    import logging
    import urllib.request

    log = logging.getLogger(__name__)
    if getattr(config, "FORCE_GC_BEFORE_WAN", True):
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass
    server = server_address or config.COMFYUI_HOST
    payload = json.dumps(
        {"unload_models": unload_models, "free_memory": free_memory}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"http://{server}/free",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ok = False
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
            ok = 200 <= getattr(resp, "status", 200) < 300
    except Exception as exc:  # noqa: BLE001
        log.warning("VRAM flush /free failed: %s", exc)
        ok = False
    settle = float(getattr(config, "WAN_FLUSH_SLEEP_SEC", 5.0))
    time.sleep(max(5.0, settle))  # let CUDA allocator settle on 12GB
    if getattr(config, "FORCE_GC_BEFORE_WAN", True):
        gc.collect()
    log.info(
        "VRAM flush: unload_models=%s free_memory=%s ok=%s settle=%.1fs",
        unload_models,
        free_memory,
        ok,
        settle,
    )
    return ok


def compose_vertical_split(
    top_clip,
    bottom_clip,
    *,
    out_w: int,
    out_h: int,
    duration: float | None = None,
):
    """Stack two clips into one 9:16 frame (top/bottom halves) — true programmatic split."""
    from moviepy.editor import clips_array

    half_h = int(out_h) // 2
    dur = float(duration) if duration is not None else min(float(top_clip.duration), float(bottom_clip.duration))

    def _fit_half(clip):
        c = clip.subclip(0, min(float(clip.duration), dur)) if float(clip.duration) > dur + 0.02 else clip
        # Cover half-frame: scale then center-crop
        scale = max(out_w / max(c.w, 1), half_h / max(c.h, 1))
        c = c.resize(scale)
        c = c.crop(
            x_center=c.w / 2,
            y_center=c.h / 2,
            width=min(c.w, out_w),
            height=min(c.h, half_h),
        )
        if c.w != out_w or c.h != half_h:
            c = c.resize(newsize=(out_w, half_h))
        return c.set_duration(dur)

    top = _fit_half(top_clip)
    bot = _fit_half(bottom_clip)
    stacked = clips_array([[top], [bot]])
    stacked = stacked.set_duration(dur)
    # Ensure exact canvas
    if stacked.w != out_w or stacked.h != out_h:
        stacked = stacked.resize(newsize=(out_w, out_h))
    return stacked


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


def build_analog_horror_bed(
    duration: float,
    *,
    glitch_at: float = 6.0,
    out_path: Path,
    loop_end_silence: float = 0.5,
    pre_glitch_gain: float = 1.0,
    post_glitch_gain: float = 1.0,
) -> Path:
    """Low drone + irregular breath; jarring static/sub thud at glitch_at; dead silence at end."""
    import wave

    import numpy as np

    duration = max(1.0, float(duration))
    sr = 44100
    n = int(duration * sr)
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(66)
    drone = 0.07 * np.sin(2 * np.pi * 38 * t) + 0.045 * np.sin(2 * np.pi * 52 * t)
    breath = 0.018 * rng.normal(0, 1, n) * (0.45 + 0.55 * np.sin(2 * np.pi * 0.12 * t))
    audio = (drone + breath).astype(np.float64)
    g0 = int(max(0.0, glitch_at) * sr)
    # Duck pre-hit bed so the glitch spike reads harder
    pre_g = max(0.05, float(pre_glitch_gain))
    post_g = max(0.05, float(post_glitch_gain))
    if g0 > 0:
        audio[:g0] *= pre_g
    if g0 < n:
        audio[g0:] *= post_g
    g1 = min(n, g0 + int(0.42 * sr))
    if g1 > g0:
        hann = np.hanning(g1 - g0)
        screech = 0.42 * rng.normal(0, 1, g1 - g0) * hann
        # Harsh mid buzz
        buzz = 0.22 * np.sin(2 * np.pi * 1800 * np.arange(g1 - g0) / sr) * hann
        audio[g0:g1] += screech + buzz
        thud_n = int(0.18 * sr)
        tt = np.arange(thud_n) / sr
        thud = 0.55 * np.sin(2 * np.pi * 42 * tt) * np.exp(-tt * 20)
        audio[g0 : min(n, g0 + thud_n)] += thud[: max(0, min(n, g0 + thud_n) - g0)]
    # Absolute zero on the final half-second (seamless loop scare)
    sil = int(max(0.05, float(loop_end_silence)) * sr)
    # Soft fade into the mute so it doesn't click
    fade_n = min(sil, int(0.35 * sr))
    if fade_n > 1 and n > fade_n:
        ramp = np.linspace(1.0, 0.0, fade_n)
        audio[n - fade_n : n] *= ramp
    audio[-sil:] = 0.0
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return out_path


def build_wind_rush_bed(
    duration: float,
    *,
    out_path: Path,
    whoosh_at: float = 5.0,
    loop_end_silence: float = 0.35,
) -> Path:
    """High-altitude wind bed for action flight Reels — continuous rush + mid whoosh."""
    import wave

    import numpy as np

    duration = max(1.0, float(duration))
    sr = 44100
    n = int(duration * sr)
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(501)
    noise = rng.normal(0, 1, n).astype(np.float64)
    # Crude band emphasis via differencing (air rush)
    rush = np.zeros(n, dtype=np.float64)
    rush[1:] = noise[1:] - 0.92 * noise[:-1]
    rush = rush / (np.max(np.abs(rush)) + 1e-8)
    low = 0.10 * np.sin(2 * np.pi * 55 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.35 * t))
    audio = 0.22 * rush + low

    w0 = int(max(0.0, float(whoosh_at)) * sr)
    wh_n = int(0.9 * sr)
    if w0 < n:
        tt = np.arange(min(wh_n, n - w0), dtype=np.float64) / sr
        env = np.sin(np.pi * np.clip(tt / 0.9, 0, 1)) ** 2
        whoosh = 0.35 * rng.normal(0, 1, len(tt)) * env
        whoosh[1:] = whoosh[1:] - 0.85 * whoosh[:-1]
        audio[w0 : w0 + len(tt)] += whoosh

    sil = int(max(0.05, float(loop_end_silence)) * sr)
    fade_n = min(sil, int(0.2 * sr))
    if fade_n > 1 and n > fade_n:
        audio[n - fade_n : n] *= np.linspace(1.0, 0.0, fade_n)
    audio[-sil:] *= 0.15
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return out_path


def build_lofi_echo_bed(
    duration: float,
    *,
    collapse_at: float = 8.0,
    out_path: Path,
    loop_end_silence: float = 0.5,
) -> Path:
    """Muffled introspective lo-fi bed; crisp chime + soft guitar at collapse; mute tail."""
    import wave

    import numpy as np

    duration = max(1.0, float(duration))
    sr = 44100
    n = int(duration * sr)
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(808)

    # Muffled lo-fi: soft kick + dusty hat + warm pad
    kick = 0.09 * np.sin(2 * np.pi * 55 * t) * (np.sin(2 * np.pi * 1.7 * t) > 0.92).astype(float)
    hat = 0.012 * rng.normal(0, 1, n) * (np.sin(2 * np.pi * 6.8 * t) > 0.7).astype(float)
    pad = (
        0.045 * np.sin(2 * np.pi * 110 * t)
        + 0.03 * np.sin(2 * np.pi * 164.8 * t)
        + 0.02 * np.sin(2 * np.pi * 220 * t)
    ) * (0.55 + 0.45 * np.sin(2 * np.pi * 0.08 * t))
    dust = 0.008 * rng.normal(0, 1, n)
    audio = (kick + hat + pad + dust).astype(np.float64)

    # Collapse hit @ 8s: crystal chime + gentle acoustic strum
    c0 = int(max(0.0, collapse_at) * sr)
    chime_n = int(1.2 * sr)
    if c0 < n:
        tt = np.arange(min(chime_n, n - c0), dtype=np.float64) / sr
        env = np.exp(-tt * 2.8)
        chime = (
            0.28 * np.sin(2 * np.pi * 1046.5 * tt)
            + 0.16 * np.sin(2 * np.pi * 1318.5 * tt)
            + 0.10 * np.sin(2 * np.pi * 1568.0 * tt)
        ) * env
        strum = (
            0.14 * np.sin(2 * np.pi * 196.0 * tt)
            + 0.11 * np.sin(2 * np.pi * 246.9 * tt)
            + 0.08 * np.sin(2 * np.pi * 293.7 * tt)
        ) * np.exp(-tt * 3.5)
        audio[c0 : c0 + len(tt)] += chime + strum

    sil = int(max(0.05, float(loop_end_silence)) * sr)
    fade_n = min(sil, int(0.25 * sr))
    if fade_n > 1 and n > fade_n:
        audio[n - fade_n : n] *= np.linspace(1.0, 0.0, fade_n)
    audio[-sil:] = 0.0
    # Instant cut to silence at ~11.9 if requested via duration
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return out_path


def load_lyric_cues(path: str | Path) -> list[dict]:
    """Load timed lyric cues from SunoX-style lyric_alignment.json."""
    import json

    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    cues = data.get("cues") if isinstance(data, dict) else data
    out: list[dict] = []
    for c in cues or []:
        if not isinstance(c, dict):
            continue
        text = str(c.get("text") or "").strip()
        if not text:
            continue
        start = float(c.get("start") or 0.0)
        end = float(c.get("end") or start)
        if end <= start:
            end = start + 0.4
        out.append(
            {
                "start": start,
                "end": end,
                "text": text,
                "section": str(c.get("section") or ""),
                "is_chorus": bool(c.get("is_chorus")),
            }
        )
    return out


def ken_burns_clip(
    still_path: str | Path,
    duration: float,
    *,
    out_w: int,
    out_h: int,
    zoom_end: float = 1.06,
):
    """Slow Ken Burns push on a still → MoviePy clip at out_w×out_h."""
    from moviepy.editor import ImageClip

    duration = max(0.1, float(duration))
    still_path = Path(still_path)
    base = ImageClip(str(still_path)).set_duration(duration)
    # Cover canvas then slow zoom
    scale0 = max(out_w / max(base.w, 1), out_h / max(base.h, 1))
    z0, z1 = float(scale0), float(scale0) * float(zoom_end)

    def _zoom(get_frame, t):
        import numpy as np
        from PIL import Image

        frame = get_frame(t)
        img = Image.fromarray(frame)
        prog = 0.0 if duration <= 0 else min(1.0, max(0.0, float(t) / duration))
        z = z0 + (z1 - z0) * prog
        nw, nh = max(out_w, int(img.width * z)), max(out_h, int(img.height * z))
        img = img.resize((nw, nh), Image.LANCZOS)
        left = max(0, (nw - out_w) // 2)
        top = max(0, (nh - out_h) // 2)
        img = img.crop((left, top, left + out_w, top + out_h))
        return np.asarray(img)

    clip = base.fl(_zoom, apply_to=["mask"])
    return clip.resize((out_w, out_h)).set_duration(duration)


def apply_cinematic_layering(clip, *, grade: str | None = None):
    """35mm-ish post: film grain + vignette + gamma/contrast grade on final stitch.

    Deepens shadows from lighting_bible and kills flat digital look.
    """
    import logging

    import numpy as np

    log = logging.getLogger(__name__)
    if not getattr(config, "ENABLE_CINEMATIC_LAYERING", True):
        return clip

    if (grade or "") == "music_soft":
        grain = float(getattr(config, "MUSIC_MV_GRAIN", 0.012))
        vig_s = float(getattr(config, "MUSIC_MV_VIGNETTE", 0.18))
        gamma = float(getattr(config, "MUSIC_MV_GAMMA", 0.95))
        contrast = float(getattr(config, "MUSIC_MV_CONTRAST", 1.05))
    else:
        grain = float(getattr(config, "CINE_GRAIN_STRENGTH", 0.028))
        vig_s = float(getattr(config, "CINE_VIGNETTE_STRENGTH", 0.32))
        gamma = float(getattr(config, "CINE_GAMMA", 0.9))
        contrast = float(getattr(config, "CINE_CONTRAST", 1.1))

    h, w = int(clip.h), int(clip.w)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    # Radial falloff — soft vignette toward edges
    dist = np.sqrt(((yy - cy) / max(cy, 1.0)) ** 2 + ((xx - cx) / max(cx, 1.0)) ** 2)
    vignette = 1.0 - vig_s * np.clip((dist - 0.35) / 0.85, 0.0, 1.0) ** 1.4
    vignette = vignette.astype(np.float32)[..., None]

    # gamma<1 via power 1/gamma deepens mid-shadows (chiaroscuro)
    power = 1.0 / max(gamma, 0.05)

    def _process(get_frame, t):
        frame = np.asarray(get_frame(t), dtype=np.float32) / 255.0
        # Contrast around mid-gray
        frame = (frame - 0.5) * contrast + 0.5
        frame = np.clip(frame, 0.0, 1.0)
        frame = np.power(frame, power)
        # Temporal film grain (per-frame seed)
        seed = int(round(float(t) * 24.0)) & 0xFFFFFFFF
        rng = np.random.default_rng(seed)
        noise = rng.normal(0.0, grain, frame.shape).astype(np.float32)
        frame = frame + noise
        frame = frame * vignette
        return (np.clip(frame, 0.0, 1.0) * 255.0).astype(np.uint8)

    out = clip.fl(_process)
    log.info(
        "Cinematic layering ON (grain=%.3f vignette=%.2f gamma=%.2f contrast=%.2f)",
        grain,
        vig_s,
        gamma,
        contrast,
    )
    return out
