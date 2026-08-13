"""P2 character LoRA paths + readiness."""
from __future__ import annotations

from pathlib import Path

import config

COMFY = Path(r"C:\ComfyUI")
DEFAULT_SLUG = "ar_filter_viewer"
DEFAULT_TRIGGER = "dxc_arviewer"
DEFAULT_LORA_NAME = "dxc_arviewer.safetensors"


def character_root(slug: str = DEFAULT_SLUG) -> Path:
    return config.ROOT / "assets" / "characters" / slug


def bible_dir(slug: str = DEFAULT_SLUG) -> Path:
    return character_root(slug) / "bible"


def lora_path(name: str = DEFAULT_LORA_NAME) -> Path:
    return COMFY / "models" / "loras" / name


def bible_ready(slug: str = DEFAULT_SLUG, *, min_images: int = 12) -> bool:
    d = bible_dir(slug)
    if not d.is_dir():
        return False
    n = len(list(d.glob("bible_*.png")))
    return n >= min_images


def lora_ready(name: str = DEFAULT_LORA_NAME, *, min_mb: float = 10) -> bool:
    p = lora_path(name)
    return p.is_file() and p.stat().st_size >= min_mb * 1024 * 1024


def ipadapter_lora_workflow() -> Path:
    return config.ROOT / "workflows" / "flux_t2i_ipadapter_lora_gguf_api.json"


def resolve_flux_workflow_p2() -> Path | None:
    """Prefer IP-Adapter+LoRA graph when character LoRA exists."""
    wf = ipadapter_lora_workflow()
    if lora_ready() and wf.exists():
        return wf
    return None
