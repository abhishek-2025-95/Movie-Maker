"""Quality OS P1 preflight — Real-ESRGAN + Flux IP-Adapter weights/nodes."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import config

COMFY = Path(r"C:\ComfyUI")


@dataclass
class PreflightResult:
    ok: bool
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    realesrgan: bool = False
    ipadapter: bool = False
    clip_vision: bool = False
    xflux_node: bool = False

    def __str__(self) -> str:
        return (
            f"PreflightResult(ok={self.ok}, realesrgan={self.realesrgan}, "
            f"ipadapter={self.ipadapter}, clip_vision={self.clip_vision}, "
            f"xflux_node={self.xflux_node}, missing={self.missing})"
        )


def _exists(path: Path, min_mb: float) -> bool:
    if not path.is_file():
        return False
    return path.stat().st_size >= min_mb * 1024 * 1024


def check_p1(
    *,
    require_realesrgan: bool = True,
    require_ipadapter: bool = True,
) -> PreflightResult:
    missing: list[str] = []
    notes: list[str] = []

    esr = COMFY / "models" / "upscale_models" / "RealESRGAN_x2plus.pth"
    ipa = COMFY / "models" / "xlabs" / "ipadapters" / "ip_adapter.safetensors"
    clip = COMFY / "models" / "clip_vision" / "clip-vit-large-patch14.safetensors"
    node = COMFY / "custom_nodes" / "x-flux-comfyui" / "nodes.py"

    realesrgan = _exists(esr, 50)
    ipadapter = _exists(ipa, 400)
    clip_vision = _exists(clip, 300)
    xflux_node = node.is_file()

    if require_realesrgan and not realesrgan:
        missing.append(str(esr))
    if require_ipadapter and not ipadapter:
        missing.append(str(ipa))
    if require_ipadapter and not clip_vision:
        missing.append(str(clip))
    if require_ipadapter and not xflux_node:
        missing.append(str(node))

    if realesrgan:
        notes.append("RealESRGAN_x2plus ready")
    if ipadapter and clip_vision and xflux_node:
        notes.append("Flux IP-Adapter (XLabs) ready")
    elif require_ipadapter:
        notes.append("Run scripts/download_quality_os_p1_weights.ps1 then restart Comfy")

    ok = len(missing) == 0
    return PreflightResult(
        ok=ok,
        missing=missing,
        notes=notes,
        realesrgan=realesrgan,
        ipadapter=ipadapter,
        clip_vision=clip_vision,
        xflux_node=xflux_node,
    )


def ipadapter_workflow_ready() -> bool:
    r = check_p1(require_realesrgan=False, require_ipadapter=True)
    return bool(r.ipadapter and r.clip_vision and r.xflux_node)


def resolve_flux_workflow_quality() -> Path:
    """Prefer IP-Adapter+LoRA (P2) → IP-Adapter (P1) → base Flux GGUF."""
    try:
        from quality_os.character_lora import resolve_flux_workflow_p2

        p2 = resolve_flux_workflow_p2()
        if p2 is not None:
            return p2
    except Exception:
        pass
    ip_wf = config.ROOT / "workflows" / "flux_t2i_ipadapter_gguf_api.json"
    if ipadapter_workflow_ready() and ip_wf.exists():
        return ip_wf
    return config.resolve_workflow_flux()
