"""Quality OS Wan routing — two-pass MoE on 12GB."""
from __future__ import annotations

import json
from pathlib import Path

import config


def should_use_two_pass() -> bool:
    return bool(getattr(config, "QUALITY_FIRST", True))


def wan_quality_steps() -> int:
    return max(14, int(getattr(config, "WAN_QUALITY_STEPS", 14) or 14))


def wan_quality_cfg() -> float:
    return float(getattr(config, "WAN_QUALITY_CFG", 4.5) or 4.5)


def _upscale_mode() -> str:
    if getattr(config, "EXPORT_USE_REALESRGAN", False):
        try:
            from quality_os.upscale import realesrgan_available

            if realesrgan_available():
                return "realesrgan_x2"
        except Exception:
            pass
    if getattr(config, "EXPORT_UPSCALE_HQ_CHAIN", False):
        return "hq_chain"
    if getattr(config, "EXPORT_UPSCALE_UNSHARP", False):
        return "unsharp"
    return "lanczos"


def write_quality_run_report(work: Path, **extra) -> Path:
    report = {
        "quality_first": bool(getattr(config, "QUALITY_FIRST", True)),
        "wan_path": "two_pass_moe" if should_use_two_pass() else "single_pass",
        "wan_steps": wan_quality_steps(),
        "wan_cfg": wan_quality_cfg(),
        "flux_steps": int(getattr(config, "FLUX_STEPS", 24)),
        "upscale": _upscale_mode(),
        "freeze_pad": bool(getattr(config, "QUALITY_ALLOW_FREEZE_PAD", False)),
        "ken_burns_fallback": bool(getattr(config, "QUALITY_ALLOW_KEN_BURNS_FALLBACK", False)),
    }
    report.update(extra)
    work.mkdir(parents=True, exist_ok=True)
    out = work / "quality_run_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return out


def render_scene_wan_two_pass(
    *,
    still: Path,
    visual: str,
    motion: str,
    prefix: str,
    seed: int,
    neg: str,
    ww: int,
    wh: int,
    length: int,
    work: Path,
) -> Path:
    import sys

    root = Path(__file__).resolve().parent
    scripts = root / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from wan_two_pass_moe import two_pass_wan as _tp

    out = work / f"{prefix}_twopass.mp4"
    _tp(
        still,
        visual=visual,
        motion=motion,
        prefix=prefix,
        seed=seed,
        neg=neg,
        out_mp4=out,
        ww=ww,
        wh=wh,
        length=int(length),
        steps=wan_quality_steps(),
        cfg=wan_quality_cfg(),
    )
    return out
