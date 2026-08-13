"""Romance Wan premium — Flux stills → Wan 2.2 I2V on all 8 beats → assemble ~120s.

Dinner-pro hardened path: hard Comfy restart per Wan, size ladder, length ladder.
Refuse Ken Burns — require real Wan mp4s.
"""
from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from comfy_runner import (
    apply_scene_to_workflow,
    load_workflow,
    pick_best_output,
    run_workflow,
)
from director import TopicJob, generate_screenplay
from editor import assemble_video
from pipeline import _scene_visual_for_flux, _wan_length_for_seconds
from utils import new_client_id, restart_comfyui
from voice import synthesize

log = logging.getLogger("romance_wan_premium")

sys.path.insert(0, str(ROOT / "scripts"))
from wan_two_pass_moe import two_pass_wan  # noqa: E402

WORK = ROOT / "temp" / "romance_wan_premium_v4"
OUT = ROOT / "final_outputs" / "Mumbai_Rain_Metro_Love_Story_Wan_Premium_v4.mp4"
TOPIC = (
    "Mumbai Rain Metro Love Story Wan Premium v4 — 2-minute 8-beat Flux then Wan 2.2 two-pass MoE"
)

# Two-process MoE (high SaveLatent → Comfy restart → low) — avoids torch_cpu.dll AV
# when both 14B UNETs share one process on RTX 5070 12GB.
# Proven smoke: 480x832 length=49 steps=10 two-pass → faces match Flux (mae≈22).
WAN_SIZE_LADDER = [(480, 832), (576, 1024)]
WAN_LENGTH_LADDER = [65, 49, 81]
WAN_CFG = 4.5
WAN_STEPS = 10
SEED_BASE = 27072740
USE_TWO_PASS_MOE = True
HIGH_NOISE_ONLY = False


def _ensure_comfy() -> None:
    import urllib.request

    try:
        urllib.request.urlopen(f"http://{config.COMFYUI_HOST}/system_stats", timeout=3)
        log.info("ComfyUI already up")
        return
    except Exception:
        pass
    if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
        raise RuntimeError("Failed to start ComfyUI")


def _set_wan_params(wf: dict, *, length: int, cfg: float, w: int, h: int) -> None:
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        inputs = node.setdefault("inputs", {})
        if node.get("class_type") == "WanImageToVideo":
            inputs["length"] = int(length)
            inputs["width"] = int(w)
            inputs["height"] = int(h)
        if node.get("class_type") in {"KSampler", "KSamplerAdvanced"} and "cfg" in inputs:
            inputs["cfg"] = float(cfg)


def _bump_steps(wf: dict, steps: int = 14) -> None:
    half = max(4, steps // 2)
    for node in wf.values():
        if not isinstance(node, dict) or node.get("class_type") != "KSamplerAdvanced":
            continue
        inputs = node.setdefault("inputs", {})
        inputs["steps"] = steps
        if str(inputs.get("add_noise", "")).lower() == "enable":
            inputs["end_at_step"] = half
        elif str(inputs.get("add_noise", "")).lower() == "disable":
            inputs["start_at_step"] = half


def _stage(plate: Path, name: str, size: tuple[int, int]) -> str:
    from PIL import Image

    config.COMFYUI_INPUT.mkdir(parents=True, exist_ok=True)
    dest = config.COMFYUI_INPUT / name
    Image.open(plate).convert("RGB").resize(size, Image.LANCZOS).save(dest, format="PNG")
    return name


def _flux_still(prompt: str, prefix: str, seed: int, neg: str) -> Path:
    fw, fh = config.RATIO_SIZES["9:16"]
    last_err: Exception | None = None
    for attempt in range(1, 3):
        if attempt > 1 or not _comfy_up():
            log.info("Flux attempt %s — restarting ComfyUI", attempt)
            if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
                raise RuntimeError("ComfyUI restart before Flux failed")
        flux_wf = load_workflow(config.WORKFLOW_FLUX)
        job = apply_scene_to_workflow(
            flux_wf,
            visual_prompt=prompt,
            motion_prompt="",
            filename_prefix=prefix,
            width=fw,
            height=fh,
            node_map=config.NODE_MAP_FLUX,
            include_motion_in_prompt=False,
            cinematic_suffix=config.STYLE_SUFFIX["live"],
            negative_prompt=neg,
            seed=seed + attempt - 1,
        )
        log.info("Flux %s %sx%s seed=%s attempt=%s", prefix, fw, fh, seed + attempt - 1, attempt)
        try:
            _, paths = run_workflow(job, client_id=new_client_id(), timeout_s=1200)
            best = pick_best_output(paths, prefix, allow_stale_disk=True)
            if best and best.exists():
                dest = WORK / f"{prefix}_still.png"
                shutil.copy2(best, dest)
                return dest
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            log.warning("Flux failed %s attempt %s: %s", prefix, attempt, exc)
            continue
    raise RuntimeError(f"Flux failed for {prefix}: {last_err}")


def _comfy_up() -> bool:
    import urllib.request

    try:
        urllib.request.urlopen(f"http://{config.COMFYUI_HOST}/system_stats", timeout=3)
        return True
    except Exception:
        return False


def _patch_wan_high_noise_only(job: dict, *, steps: int, cfg: float) -> dict:
    """Avoid loading low-noise 14B — torch_cpu.dll AV on MoE swap (RTX 5070)."""
    if "22" in job:
        inp = job["22"].setdefault("inputs", {})
        inp["steps"] = int(steps)
        inp["cfg"] = float(cfg)
        inp["start_at_step"] = 0
        inp["end_at_step"] = 10000
        inp["return_with_leftover_noise"] = "disable"
        inp["add_noise"] = "enable"
    if "24" in job:
        job["24"].setdefault("inputs", {})["samples"] = ["22", 0]
    for nid in ("14", "18", "23"):
        job.pop(nid, None)
    return job


def _wan_from_still(
    still: Path,
    *,
    visual: str,
    motion: str,
    prefix: str,
    seed: int,
    neg: str,
) -> Path:
    dest = WORK / f"{prefix}_wan.mp4"
    if dest.exists() and dest.stat().st_size > 100_000:
        log.info("Reuse Wan clip %s", dest.name)
        return dest

    last_err: Exception | None = None
    for length in WAN_LENGTH_LADDER:
        for ww, wh in WAN_SIZE_LADDER:
            log.info(
                "Wan try %s length=%s %sx%s two_pass=%s high_only=%s",
                prefix,
                length,
                ww,
                wh,
                USE_TWO_PASS_MOE,
                HIGH_NOISE_ONLY,
            )
            clip = None
            try:
                if USE_TWO_PASS_MOE:
                    two_pass_wan(
                        still,
                        visual=visual,
                        motion=motion,
                        prefix=prefix,
                        seed=seed,
                        neg=neg,
                        out_mp4=dest,
                        ww=ww,
                        wh=wh,
                        length=length,
                        steps=WAN_STEPS,
                        cfg=WAN_CFG,
                    )
                    (WORK / f"{prefix}_meta.txt").write_text(
                        f"{ww}x{wh} length={length} cfg={WAN_CFG} steps={WAN_STEPS} "
                        f"two_pass=1 seed={seed}\n",
                        encoding="utf-8",
                    )
                    log.info("Wan OK %s → %s (%.1f MB)", prefix, dest.name, dest.stat().st_size / 1e6)
                    return dest

                if not restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 120))):
                    raise RuntimeError("ComfyUI restart before Wan failed")
                ref = _stage(still, f"{prefix}_{ww}x{wh}.png", (ww, wh))
                wan_wf = load_workflow(config.WORKFLOW_WAN)
                wan_job = apply_scene_to_workflow(
                    wan_wf,
                    visual_prompt=visual,
                    motion_prompt=motion,
                    filename_prefix=prefix,
                    width=ww,
                    height=wh,
                    reference_image_name=ref,
                    node_map=config.NODE_MAP_WAN,
                    include_motion_in_prompt=True,
                    cinematic_suffix=config.STYLE_SUFFIX["live"],
                    negative_prompt=neg,
                    seed=seed,
                )
                _set_wan_params(wan_job, length=length, cfg=WAN_CFG, w=ww, h=wh)
                if HIGH_NOISE_ONLY:
                    _patch_wan_high_noise_only(wan_job, steps=WAN_STEPS, cfg=WAN_CFG)
                else:
                    _bump_steps(wan_job, WAN_STEPS)
                _, paths = run_workflow(wan_job, client_id=new_client_id(), timeout_s=5400)
                clip = pick_best_output(paths, prefix, allow_stale_disk=True)
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                log.warning("Wan failed %s %sx%s len=%s: %s", prefix, ww, wh, length, exc)
                continue
            if clip and clip.exists():
                shutil.copy2(clip, dest)
                (WORK / f"{prefix}_meta.txt").write_text(
                    f"{ww}x{wh} length={length} cfg={WAN_CFG} steps={WAN_STEPS} "
                    f"high_only={HIGH_NOISE_ONLY} seed={seed}\n",
                    encoding="utf-8",
                )
                log.info("Wan OK %s → %s (%.1f MB)", prefix, dest.name, dest.stat().st_size / 1e6)
                return dest
    raise RuntimeError(f"All Wan attempts failed for {prefix}: {last_err}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    WORK.mkdir(parents=True, exist_ok=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Single-process guard (ignore parents / short-lived shells)
    try:
        import psutil

        me = psutil.Process()
        my_pid = me.pid
        parent_pid = me.ppid()
        twins = []
        for p in psutil.process_iter(["pid", "cmdline"]):
            pid = p.info.get("pid")
            if pid in {my_pid, parent_pid}:
                continue
            cmd = " ".join(p.info.get("cmdline") or [])
            if "render_romance_wan_premium.py" in cmd:
                twins.append(pid)
        if twins:
            raise RuntimeError(f"Another romance Wan premium render running: pids={twins}")
    except ImportError:
        pass

    _ensure_comfy()
    job = TopicJob(topic=TOPIC, mode="character", style="live", ratio="9:16", lang="en")
    sp = generate_screenplay(job)
    assert len(sp.scenes) == 8
    assert sp.raw.get("require_wan") is True
    beat_durs = list(sp.raw.get("beat_durations") or [15.0] * 8)
    neg = config.FLUX_NEGATIVE_PROMPT

    # Prefer already-rendered Flux plates — skip Flux regen risk.
    v3_dir = ROOT / "temp" / "romance_wan_premium_v3"
    legacy_dir = ROOT / "temp" / "Mumbai_Rain_Metro_Love_Story_2-minute_8-"
    legacy0 = (
        ROOT
        / "temp"
        / "Mumbai_Rain_Metro_Love_Story_Wan_Premium"
        / "dx_Mumbai_Rain_Metro_Love_Story_Wan_Premium_s00_still.png"
    )

    clip_paths: list[Path] = []
    narr_paths: list[Path] = []

    for idx, scene in enumerate(sp.scenes):
        prefix = f"dx_rom_wan_s{idx:02d}"
        still = WORK / f"{prefix}_still.png"
        if not still.exists():
            v3_i = v3_dir / f"{prefix}_still.png"
            legacy_i = legacy_dir / f"dx_Mumbai_Rain_Metro_Love_Story_2-minute_8-_s{idx:02d}_still.png"
            if v3_i.exists():
                shutil.copy2(v3_i, still)
                log.info("Reuse v3 Flux still for beat %s", idx + 1)
            elif legacy_i.exists():
                shutil.copy2(legacy_i, still)
                log.info("Reuse Ken-Burns Flux still for beat %s", idx + 1)
            elif idx == 0 and legacy0.exists():
                shutil.copy2(legacy0, still)
                log.info("Reuse legacy Flux still for beat 1")
            else:
                visual = _scene_visual_for_flux(
                    scene, idx=idx, total=8, screenplay=sp, topic=job.topic
                )
                still = _flux_still(visual, prefix, SEED_BASE + idx * 17, neg)
        else:
            log.info("Reuse Flux still %s", still.name)

        vo = WORK / f"narration_{idx:02d}.wav"
        if not vo.exists():
            synthesize(scene.narration, lang=job.lang, out_path=vo)
        narr_paths.append(vo)

        visual = _scene_visual_for_flux(
            scene, idx=idx, total=8, screenplay=sp, topic=job.topic
        )
        wan_mp4 = _wan_from_still(
            still,
            visual=visual,
            motion=scene.motion_prompt,
            prefix=prefix,
            seed=SEED_BASE + idx * 17 + 3,
            neg=neg,
        )
        clip_paths.append(wan_mp4)
        log.info("Beat %s/%s ready", idx + 1, 8)

    transitions = [s.transition_to_next for s in sp.scenes]
    assemble_video(
        clip_paths,
        narr_paths,
        out_path=OUT,
        ratio="9:16",
        burn_captions=False,
        caption_lines=None,
        transitions=transitions,
        screenplay_meta=dict(sp.raw or {}),
    )
    log.info("DONE %s (%.1f MB) target_durs=%s", OUT, OUT.stat().st_size / 1e6, beat_durs)
    print(f"DONE {OUT}")


if __name__ == "__main__":
    main()
