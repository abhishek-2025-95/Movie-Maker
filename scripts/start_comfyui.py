"""Start ComfyUI in THIS console (visible logs). Leave the window open."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from utils import (
    comfyui_reachable,
    python_has_torch,
    resolve_comfy_python,
    running_comfy_python,
)

HF_HUB_SPEC = "huggingface-hub>=1.5.0,<2.0"


def _extra_roots() -> list[Path]:
    home = Path.home()
    return [
        Path(getattr(config, "COMFYUI_ROOT", r"C:\ComfyUI")),
        Path(r"C:\ComfyUI"),
        Path(r"C:\ComfyUI_windows_portable\ComfyUI"),
        Path(r"C:\ComfyUI_windows_portable"),
        home / "Documents" / "ComfyUI",
        home / "ComfyUI",
        Path(r"D:\ComfyUI"),
        Path(r"E:\ComfyUI"),
    ]


def find_main() -> Path | None:
    configured = Path(getattr(config, "COMFYUI_MAIN", r"C:\ComfyUI\main.py"))
    cands = [configured]
    for root in _extra_roots():
        cands.append(root / "main.py")
        cands.append(root / "ComfyUI" / "main.py")
    seen: set[str] = set()
    for p in cands:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        if p.is_file():
            return p
    return None


def diagnose(main_py: Path | None) -> None:
    print("=== ComfyUI start diagnostic ===", flush=True)
    print(f"reachable={comfyui_reachable()}", flush=True)
    print(f"COMFYUI_ROOT={config.COMFYUI_ROOT} exists={Path(config.COMFYUI_ROOT).exists()}", flush=True)
    print(f"COMFYUI_MAIN={config.COMFYUI_MAIN} exists={Path(config.COMFYUI_MAIN).is_file()}", flush=True)
    print(f"COMFYUI_PYTHON={config.COMFYUI_PYTHON} exists={Path(config.COMFYUI_PYTHON).is_file()}", flush=True)
    print(f"found_main={main_py}", flush=True)
    root = Path(config.COMFYUI_ROOT)
    if root.is_dir():
        names = sorted(p.name for p in root.iterdir())[:40]
        print(f"C:\\ComfyUI listing ({len(names)}): {', '.join(names)}", flush=True)
    live = running_comfy_python()
    print(f"running_comfy_python={live}", flush=True)
    py = resolve_comfy_python(running_exe=live, require_torch=False)
    print(f"resolve_python={py} torch={python_has_torch(py) if py else None}", flush=True)


def transformers_import_error(py: Path) -> str | None:
    """Return stderr if `import transformers` fails, else None."""
    r = subprocess.run(
        [str(py), "-c", "import transformers"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if r.returncode == 0:
        return None
    return (r.stderr or r.stdout or "import transformers failed").strip()


def repair_huggingface_hub(py: Path) -> int:
    """Install the hub range current transformers requires (seen: 1.4.1 vs >=1.5)."""
    cmd = [str(py), "-m", "pip", "install", HF_HUB_SPEC]
    print("REPAIR", " ".join(cmd), flush=True)
    return int(subprocess.call(cmd))


def ensure_transformers(py: Path) -> None:
    err = transformers_import_error(py)
    if err is None:
        print("transformers import OK", flush=True)
        return
    print("transformers import failed:", err.splitlines()[-1] if err else err, flush=True)
    if repair_huggingface_hub(py) != 0:
        raise RuntimeError(f"pip install {HF_HUB_SPEC} failed")
    err2 = transformers_import_error(py)
    if err2 is not None:
        raise RuntimeError(f"transformers still broken after hub repair:\n{err2}")
    print("transformers import OK after hub repair", flush=True)


def main() -> int:
    if comfyui_reachable():
        print("ComfyUI already healthy at http://127.0.0.1:8188 — leave it running.", flush=True)
        return 0

    main_py = find_main()
    diagnose(main_py)
    if main_py is None:
        print(
            "FATAL: main.py not found. Open ComfyUI the way you usually do, "
            "wait for the UI, then run scripts\\run_us_stoop_almost_10s_external.bat",
            flush=True,
        )
        return 1

    live = running_comfy_python()
    py = resolve_comfy_python(running_exe=live, require_torch=True)
    if py is None:
        py = resolve_comfy_python(running_exe=live, require_torch=False)
    if py is None:
        py = Path(config.COMFYUI_PYTHON)
    if not py.is_file():
        print(f"FATAL: no python.exe to launch Comfy ({py})", flush=True)
        return 1

    try:
        ensure_transformers(py)
    except RuntimeError as exc:
        print(f"FATAL {exc}", flush=True)
        return 1

    args = list(
        getattr(config, "COMFY_LAUNCH_ARGS", None)
        or ("--listen", "127.0.0.1", "--port", "8188", "--normalvram")
    )
    cmd = [str(py), str(main_py), *args]
    print("Starting ComfyUI in THIS window. Leave it open.", flush=True)
    print("CMD:", " ".join(cmd), flush=True)
    print("When you see To see the GUI go to: http://127.0.0.1:8188", flush=True)
    print("open a SECOND cmd and run scripts\\run_us_stoop_almost_10s_external.bat", flush=True)
    os.chdir(str(main_py.parent))
    return int(subprocess.call(cmd, cwd=str(main_py.parent)))


if __name__ == "__main__":
    raise SystemExit(main())
