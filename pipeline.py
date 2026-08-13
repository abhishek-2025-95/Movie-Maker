"""End-to-end topic → cinematic MP4 pipeline."""
from __future__ import annotations

import logging
import shutil
import time
import traceback
from pathlib import Path

from PIL import Image

if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS  # type: ignore[attr-defined]

import config
from comfy_runner import (
    WorkflowNotFoundError,
    _set_input,
    apply_scene_to_workflow,
    load_workflow,
    pick_best_output,
    run_workflow,
    stage_reference_image,
)
from director import Screenplay, TopicJob, generate_screenplay, style_prompts
from editor import assemble_video
from utils import (
    new_client_id,
    free_comfyui_memory,
    restart_comfyui,
    unload_ollama_gpu_models,
    force_ollama_cpu,
)
from voice import synthesize


log = logging.getLogger(__name__)


def _is_act2_scene(idx: int, scene, total: int) -> bool:
    """Middle beat of a 3-act short, or explicit ACT2 / escalation markers."""
    blob = f"{getattr(scene, 'visual_prompt', '')} {getattr(scene, 'narration', '')}".lower()
    if "act2" in blob or "act 2" in blob or "escalation" in blob or "conflict" in blob:
        return True
    if total >= 3 and idx == 1:
        return True
    if total >= 6 and idx in {2, 3}:  # 6-beat horror mid acts
        return True
    return False


def _is_act3_scene(idx: int, scene, total: int) -> bool:
    blob = f"{getattr(scene, 'visual_prompt', '')} {getattr(scene, 'narration', '')}".lower()
    if "act3" in blob or "act 3" in blob or "climax" in blob:
        return True
    if total >= 3 and idx == total - 1:
        return True
    if total >= 6 and idx >= 4:
        return True
    return False


def _is_no_people_scene(scene) -> bool:
    """Cutaway / establish plates that must stay empty of characters."""
    blob = f"{getattr(scene, 'visual_prompt', '')} {getattr(scene, 'motion_prompt', '')}".lower()
    return (
        "no faces" in blob
        or "zero people" in blob
        or "nobody visible" in blob
        or "only the waiting table" in blob
        or "table detail" in blob
        or "umbrella tip" in blob
        or "empty second chai" in blob
        or "empty ceramic chai" in blob
        or "cutaway umbrella" in blob
        or "cutaway empty promise" in blob
        or "still-life extreme close-up" in blob
        or "joined hands" in blob and "no faces" in blob
    )


def _prepend_trinity(
    visual: str,
    screenplay: Screenplay | None,
    *,
    skip_character: bool = False,
) -> str:
    """Lock identity / location / prop / lighting + sensory across all acts."""
    if screenplay is None:
        return visual or ""
    parts: list[str] = []
    char = (screenplay.character_bible or "").strip()
    loc = (screenplay.location_lock or "").strip()
    prop = (screenplay.prop_bible or "").strip()
    light = (screenplay.lighting_bible or "").strip()
    # FPV beats: never inject full-body character bible (forces chase-cam)
    if char and not skip_character:
        parts.append(f"CHARACTER_BIBLE: {char}")
    if loc:
        parts.append(f"LOCATION_LOCK: {loc}")
    if prop:
        parts.append(f"PROP_BIBLE: {prop}")
    if light:
        parts.append(f"LIGHTING_BIBLE: {light}")
    sensory = str(getattr(config, "SENSORY_BIBLE", "") or "").strip()
    if sensory:
        parts.append(sensory)
    if not parts:
        return visual or ""
    prefix = ", ".join(parts)
    body = visual or ""
    # Avoid double-prepending on retries
    if "LOCATION_LOCK:" in body and "PROP_BIBLE:" in body and "SENSORY_BIBLE:" in body:
        return body
    return f"{prefix}, {body}" if body else prefix


def _apply_character_bible(
    visual: str,
    *,
    is_act2: bool = False,
    character_bible: str = "",
    solitary: bool = False,
) -> str:
    """Prefer Dynamic Trinity character_bible; never force duo on solitary topics."""
    dyn = (character_bible or "").strip()
    a = str(getattr(config, "CHARACTER_BIBLE_A", "") or "").strip()
    b = str(getattr(config, "CHARACTER_BIBLE_B", "") or "").strip()
    duo = str(getattr(config, "CHARACTER_BIBLE", "") or "").strip()

    if dyn:
        solo = dyn
        if is_act2 or solitary:
            isolation = (
                f"SUBJECT: Solitary shot of ONLY {solo}. Completely isolated, wide staging, "
                f"no other characters in the frame, single subject only"
            )
            body = visual or ""
            return f"{isolation}, {body}" if body else isolation
        if dyn.lower() in (visual or "").lower():
            return visual
        return f"{dyn}, {visual}" if visual else dyn

    if solitary:
        solo = a or (duo.split(",")[0].strip() if duo else "single protagonist")
        isolation = (
            f"SUBJECT: Solitary shot of ONLY {solo}. Completely isolated, wide staging, "
            f"no other characters in the frame, single subject only"
        )
        body = visual or ""
        return f"{isolation}, {body}" if body else isolation

    if is_act2:
        which = str(getattr(config, "ACT2_ISOLATE_CHAR", "A") or "A").upper()
        solo = a if which != "B" else b
        if not solo:
            solo = duo.split(",")[0].strip() if duo else "single protagonist"
        isolation = (
            f"SUBJECT: Solitary shot of ONLY {solo}. Completely isolated, wide staging, "
            f"no other characters in the frame, single subject only"
        )
        body = visual or ""
        if duo and duo.lower() in body.lower():
            body = body.replace(duo, solo).replace(duo.lower(), solo)
        if a and b and a.lower() in body.lower() and b.lower() in body.lower():
            body = f"{solo}, {body}"
        return f"{isolation}, {body}" if body else isolation

    bible = duo or ", ".join(p for p in (a, b) if p)
    if not bible:
        return visual
    if bible.lower() in (visual or "").lower():
        return visual
    return f"{bible}, {visual}" if visual else bible


def _scene_negative(
    base_neg: str,
    *,
    is_act2: bool = False,
    is_act3: bool = False,
    reel_continuity: bool = False,
    face_fill: bool = False,
    action_flight: bool = False,
    is_fpv: bool = False,
    music_video: bool = False,
) -> str:
    neg = base_neg
    if is_act2:
        ban = getattr(
            config,
            "ACT2_EMOTION_NEGATIVE",
            "smiling, happy, eye contact, together, couple, two people",
        )
        neg = f"{neg}, {ban}"
    if is_act3:
        ban3 = getattr(config, "ACT3_EMOTION_NEGATIVE", "(smiling, happy, relaxed:1.5)")
        loc_ban = getattr(
            config,
            "ACT3_LOCATION_NEGATIVE",
            "(modern fluorescent lights, LED wall strips, sci-fi light bars:1.4)",
        )
        neg = f"{neg}, {ban3}, {loc_ban}"
    clock_ban = str(getattr(config, "REEL_CLOCK_NEGATIVE", "") or "").strip()
    if clock_ban and clock_ban not in neg:
        neg = f"{neg}, {clock_ban}"
    if reel_continuity:
        cont_ban = str(getattr(config, "REEL_CONTINUITY_NEGATIVE", "") or "").strip()
        if cont_ban and cont_ban not in neg:
            neg = f"{neg}, {cont_ban}"
    if face_fill:
        face_ban = str(getattr(config, "FACE_SILHOUETTE_NEGATIVE", "") or "").strip()
        if face_ban and face_ban not in neg:
            neg = f"{neg}, {face_ban}"
    if action_flight:
        # Shared fantasy-wing ban — never ban chase-cam here (body beats need it).
        flight_ban = str(getattr(config, "ACTION_FLIGHT_NEGATIVE", "") or "").strip()
        if flight_ban and flight_ban not in neg:
            neg = f"{neg}, {flight_ban}"
        if is_fpv:
            fpv_ban = str(getattr(config, "ACTION_FPV_NEGATIVE", "") or "").strip()
            if fpv_ban and fpv_ban not in neg:
                neg = f"{neg}, {fpv_ban}"
    if music_video:
        mv_ban = (
            "(letterbox, black bars, cinema bars, widescreen mattes:1.5), "
            "(woman, female, girl, gender swap, different person each shot:1.45), "
            "(duplicate faces, identity change mid-video:1.3)"
        )
        if mv_ban not in neg:
            neg = f"{neg}, {mv_ban}"
    return neg


def _score_fpv_still(path) -> float:
    """Higher = more chest-cam FPV, lower = chase-cam helmet/back.

    Heuristic on a tiny RGB downsample: chase plates put a dark helmet/shoulder
    blob in the lower-center that is much darker than the canyon mid-frame.
    True FPV keeps an open bright canyon with little/no body mass.
    """
    try:
        import numpy as np

        with Image.open(path) as im:
            arr = np.asarray(
                im.convert("RGB").resize((64, 112), Image.Resampling.BILINEAR),
                dtype=np.float32,
            )
        h, w = arr.shape[:2]
        mid = arr[int(h * 0.18) : int(h * 0.52), int(w * 0.15) : int(w * 0.85)]
        helm = arr[int(h * 0.50) : int(h * 0.90), int(w * 0.20) : int(w * 0.80)]
        bottom = arr[int(h * 0.92) :, :]
        mid_b = float(mid.mean() / 255.0)
        helm_b = float(helm.mean() / 255.0)
        # Chase-cam signature: lower-center much darker than canyon mid (helmet/back).
        contrast_penalty = 0.0
        if helm_b < mid_b * 0.72:
            contrast_penalty = (mid_b - helm_b) * 6.0
        r, g, b = bottom[:, :, 0], bottom[:, :, 1], bottom[:, :, 2]
        orange = float(((r > 110) & (r > g) & (r > (b * 0.85))).mean())
        # Prefer open canyon; light orange bottom strip is a bonus, not required.
        return (mid_b * 2.6) + (orange * 1.2) - contrast_penalty - ((1.0 - helm_b) * 0.8)
    except Exception:
        return -999.0


def _score_suit_bible_still(path) -> float:
    """Higher = technical fabric wingsuit; lower = butterfly / board fantasy wings.

    Monarch/costume plates show a tall vivid-orange span across the subject ROI.
    Technical suits keep orange as thin accent strips (small vertical extent).
    """
    try:
        import numpy as np

        with Image.open(path) as im:
            arr = np.asarray(
                im.convert("RGB").resize((96, 168), Image.Resampling.BILINEAR),
                dtype=np.float32,
            )
        h, w = arr.shape[:2]
        subj = arr[int(h * 0.22) : int(h * 0.78), int(w * 0.18) : int(w * 0.82)]
        sh, sw = subj.shape[:2]
        r, g, b = subj[:, :, 0], subj[:, :, 1], subj[:, :, 2]
        mx = subj.max(axis=2)
        mn = subj.min(axis=2)
        sat = (mx - mn) / (mx + 1e-6)
        vivid = (r > 150) & (r > (g + 40)) & (r > (b + 40)) & (sat > 0.35)
        vivid_frac = float(vivid.mean())
        rowspan_frac = 0.0
        colspan_frac = 0.0
        if vivid.any():
            rows = np.where(vivid.any(axis=1))[0]
            cols = np.where(vivid.any(axis=0))[0]
            rowspan_frac = float((rows.max() - rows.min() + 1) / max(sh, 1))
            colspan_frac = float((cols.max() - cols.min() + 1) / max(sw, 1))
        torso = subj[int(sh * 0.25) : int(sh * 0.85), int(sw * 0.30) : int(sw * 0.70)]
        torso_dark = float(1.0 - (torso.mean() / 255.0))
        # Tall + wide vivid orange ≈ butterfly / board wings.
        wing_penalty = (rowspan_frac * 3.8) + (colspan_frac * rowspan_frac * 4.5) + (
            vivid_frac * 8.0
        )
        score = (torso_dark * 2.0) - wing_penalty
        if rowspan_frac > 0.38 and colspan_frac > 0.45:
            score -= 3.0
        return score
    except Exception:
        return -999.0


def _bump_wan_sampler_steps(workflow: dict, steps: int) -> None:
    """Raise both Wan KSamplerAdvanced step counts and keep the high/low split."""
    steps = max(8, int(steps))
    half = max(4, steps // 2)
    advanced = [
        n
        for n in workflow.values()
        if isinstance(n, dict) and n.get("class_type") == "KSamplerAdvanced"
    ]
    for node in advanced:
        inputs = node.setdefault("inputs", {})
        inputs["steps"] = steps
        if str(inputs.get("add_noise", "")).lower() == "enable":
            inputs["end_at_step"] = half
        elif str(inputs.get("add_noise", "")).lower() == "disable":
            inputs["start_at_step"] = half


def _inject_face_fill(visual: str) -> str:
    face = str(getattr(config, "FACE_FILL_POSITIVE", "") or "").strip()
    body = visual or ""
    if face and "soft front fill light" not in body.lower():
        body = f"{body}, {face}" if body else face
    return body


def _inject_reel_prop_lock(
    visual: str,
    *,
    continuity: bool = False,
    clock: bool = True,
) -> str:
    """Optional HH:MM clock (phone reels) + locked-POV continuity language."""
    body = visual or ""
    if clock:
        clock_pos = str(getattr(config, "REEL_CLOCK_POSITIVE", "") or "").strip()
        if (
            clock_pos
            and "HH:MM" not in body
            and "rectangular digital" not in body.lower()
        ):
            body = f"{body}, {clock_pos}" if body else clock_pos
    if continuity:
        cont = str(getattr(config, "REEL_CONTINUITY_POSITIVE", "") or "").strip()
        # Phone-nightstand continuity phrase — skip for action oneshot (chase cam).
        if cont and "locked off camera" not in body.lower() and clock:
            body = f"{body}, {cont}" if body else cont
    return body


def _is_continuity_reel(job: TopicJob, screenplay: Screenplay) -> bool:
    meta = screenplay.raw or {}
    if "continuity_i2v" in meta:
        return bool(meta.get("continuity_i2v"))
    if meta.get("reel_profile") == "analog_phone_12s":
        return True
    return False


def _wan_length_for_seconds(sec: float) -> int:
    """Wan frame count @ ~16fps for a target beat duration."""
    return max(24, int(round(float(sec) * 16.0)))


def _scene_visual_for_flux(
    scene,
    *,
    idx: int,
    total: int,
    screenplay: Screenplay | None = None,
    topic: str = "",
) -> str:
    raw = (screenplay.raw if screenplay else None) or {}
    # Echo Chamber / face-fill: skip Act-2 isolation + Act-3 smile bans in the VISUAL too
    skip_act_emotion = bool(
        raw.get("compose_plan")
        or raw.get("face_fill")
        or raw.get("skip_act_emotion")
        or raw.get("action_flight")
        or raw.get("reel_profile")
        in {
            "echo_chamber_12s",
            "wingsuit_15s",
            "wingsuit_oneshot_15s",
            "usa_sports_quiz_12s",
        }
    )
    is_act2 = (not skip_act_emotion) and _is_act2_scene(idx, scene, total)
    is_act3 = (not skip_act_emotion) and _is_act3_scene(idx, scene, total)
    solitary = False
    try:
        from director import topic_implies_solitary

        solitary = topic_implies_solitary(topic or (screenplay.title if screenplay else ""))
    except Exception:
        solitary = False
    fpv_idxs = {int(x) for x in (raw.get("fpv_scene_indices") or [])}
    is_fpv = idx in fpv_idxs
    skip_char = bool(raw.get("skip_character_bible")) or is_fpv or _is_no_people_scene(scene)
    char_bible = (screenplay.character_bible if screenplay else "") or ""
    if skip_char:
        # FPV / stadium quiz / empty cutaways — never inject default romance duo bible
        visual = scene.visual_prompt or ""
        visual = _prepend_trinity(visual, screenplay, skip_character=True)
    else:
        visual = _apply_character_bible(
            scene.visual_prompt,
            is_act2=is_act2,
            character_bible=char_bible,
            solitary=solitary,
        )
        visual = _prepend_trinity(visual, screenplay)
    if is_fpv:
        fpv_pos = str(getattr(config, "ACTION_FPV_POSITIVE", "") or "").strip()
        if fpv_pos and "chest-mount" not in visual.lower():
            visual = f"{fpv_pos}, {visual}" if visual else fpv_pos
    if is_act2:
        emo = getattr(config, "ACT2_EMOTION_POSITIVE", "")
        missing = [
            k
            for k in ("looking away", "solitary", "sad expression", "distance")
            if k not in visual.lower()
        ]
        if missing or emo:
            visual = f"{visual}, {emo}" if emo else f"{visual}, {', '.join(missing)}"
    # Act-3: reinforce ancient location DNA (kill modern light-bar corridors)
    if is_act3 and screenplay and (screenplay.location_lock or "").strip():
        visual = (
            f"{visual}, LOCATION_LOCK reinforced: {screenplay.location_lock}, "
            "ancient sandstone only, torch and oil-lamp practicals, hieroglyph walls, "
            "no modern lighting fixtures"
        )
    # Prop must stay mechanically readable even in wide / distant shots
    prop = (screenplay.prop_bible if screenplay else "") or ""
    reelish = bool(
        screenplay
        and (
            (screenplay.raw or {}).get("reel_profile") == "analog_phone_12s"
            or (screenplay.raw or {}).get("continuity_i2v")
            or (screenplay.raw or {}).get("director_mode") == "raw"
        )
    )
    if prop.strip() and not reelish:
        wide = str(
            getattr(
                config,
                "PROP_WIDE_VISIBILITY",
                "prop clearly readable with visible brass gears, no featureless glowing orb",
            )
        ).strip()
        if wide and "featureless glowing orb" not in visual.lower():
            visual = f"{visual}, {wide}"
    # Always fight Wan softness / micro-blur before Flux + Wan submit
    sharp = str(
        getattr(
            config,
            "VISUAL_SHARPNESS_SUFFIX",
            "(ultra-sharp focus, highly detailed, 8k resolution, crisp cinematic lighting:1.2)",
        )
    ).strip()
    if sharp and "ultra-sharp focus" not in visual.lower():
        visual = f"{visual}, {sharp}"
    # Music video v2: force full-bleed 16:9 (kill baked letterbox) + identity reminder
    if screenplay and (screenplay.raw or {}).get("reel_profile") == "music_video_lyric_180s":
        if "no letterbox" not in visual.lower():
            visual = (
                f"{visual}, full-bleed 16:9 edge-to-edge frame, "
                "no letterbox, no black bars, no cinema bars"
            )
        bible = (screenplay.character_bible or "").strip()
        if bible and "SAME young man" not in visual:
            visual = f"{bible}, {visual}"
    return visual


def _complete_vo_lines(topic: str) -> tuple[str, ...]:
    """Full 15–20 word replacements — never appended as second clauses."""
    tl = (topic or "").lower()
    if "tomb" in tl or "egypt" in tl or "artifact" in tl:
        return (
            "Sandstorms have swallowed the past, leaving only whispers inside this forgotten chamber of cold stone.",
            "In the dust-thick dark she finds a core that breathes like something almost alive tonight.",
            "The winds of time howl down the corridor, warning that this relic must never wake fully.",
        )
    if "server" in tl or "ai" in tl:
        return (
            "Cold light crawls along the racks as the machine quietly learns the sound of her name.",
            "Silence fractures while the servers answer back in a voice that is no longer human.",
            "One final switch remains between control and something that will refuse to sleep again tonight.",
        )
    if (
        "dinner" in tl
        or "candlelight" in tl
        or "candlelit" in tl
        or "restaurant" in tl
    ):
        return (
            "Two quiet voices take their seats while the empty dining room finally softens around them.",
            "The candle keeps watch while the room holds its breath between their quiet words tonight.",
            "They share a quiet laugh while the candle holds every secret close between them here tonight.",
        )
    if (
        "love" in tl
        or "romance" in tl
        or "romantic" in tl
        or "metro" in tl
        or "mumbai" in tl
        or "umbrella" in tl
    ):
        return (
            "Mumbai monsoon rain traps two strangers under one borrowed umbrella, and neither looks away first.",
            "They share a few quiet steps under one navy umbrella while the city keeps rushing past them.",
            "Rain beads on the umbrella tip while their hands almost meet on the wooden handle tonight.",
            "One missed call stretches into an empty night, and she stands alone where their promise used to live.",
            "An empty second chai cup waits on the railing while her dark phone refuses to light up again.",
            "Same rain, same platform, and this time their joined hands refuse to let the city win again.",
            "Quiet eye contact returns under the rain while hope softens every hard silence between them.",
            "Joined hands fill the frame while soft rain keeps every promise they almost lost tonight.",
        )
    return (
        "Shadows lean closer tonight as the unseen truth finally steps into the waiting frame now.",
        "Breath catches hard in the dark while fate refuses to stay quiet any longer here.",
        "One irreversible choice will seal whatever this trembling moment becomes for everyone forever.",
    )


def _enforce_narration_density(scenes: list, *, topic: str = "") -> list:
    """Guarantee unique complete 15–20 word VO lines — never glue density-pad second clauses."""
    from director import Scene

    min_w = int(getattr(config, "NARRATION_MIN_WORDS", 15))
    max_w = int(getattr(config, "NARRATION_MAX_WORDS", 20))
    seen: set[str] = set()
    out = []
    completes = list(_complete_vo_lines(topic))
    # Guarantee each bank line is in range
    for i, line in enumerate(completes):
        w = line.split()
        if len(w) < min_w:
            completes[i] = (line.rstrip(".") + " beneath the waiting night.").strip()
            w = completes[i].split()
        if len(w) > max_w:
            completes[i] = " ".join(w[:max_w]).rstrip(".,;:") + "."
    banned = (
        "every second counts",
        "truth refuses to stay buried",
        "sand drifts through the dark",
        "dust thickens while something ancient",
        "something irreversible is already in motion",
    )
    pad_starts = (
        "sand drifts",
        "dust thickens",
        "one trembling reach",
        "cold light crawls",
        "silence fractures",
        "one switch remains",
        "shadows lean closer",
        "breath catches hard",
        "one final choice",
        "something irreversible",
    )
    next_bank = 0
    for i, sc in enumerate(scenes):
        text = " ".join((sc.narration or "").strip().split())
        # Strip glued density-pad second clauses (e.g. "Foo. Sand drifts…")
        if ". " in text:
            first, rest = text.split(". ", 1)
            rest_l = rest.lower()
            if any(rest_l.startswith(p) for p in pad_starts) or any(b in rest_l for b in banned):
                text = first.rstrip(".") + "."
        if any(b in text.lower() for b in banned):
            text = ""
        words = text.split() if text else []
        key = text.lower()
        needs_replace = (
            not text
            or key in seen
            or len(words) < min_w
            or len(words) > max_w
            or not text.rstrip().endswith((".", "!", "?"))
        )
        if needs_replace:
            # Pick next unused complete line from the bank (rotate, never append)
            picked = None
            for _ in range(len(completes) * 2):
                candidate = completes[next_bank % len(completes)]
                next_bank += 1
                if candidate.lower() not in seen:
                    picked = candidate
                    break
            text = picked or completes[i % len(completes)]
            words = text.split()
        if len(words) > max_w:
            words = words[:max_w]
            text = " ".join(words).rstrip(".,;:") + "."
        seen.add(text.lower())
        out.append(
            Scene(
                narration=text,
                visual_prompt=sc.visual_prompt,
                motion_prompt=sc.motion_prompt,
                transition_to_next=sc.transition_to_next,
            )
        )
        log.info("Scene %s narration density OK (%s words)", i + 1, len(text.split()))
    return out


def _flush_before_wan(*, reason: str = "pre-Wan", hard_restart: bool = False) -> None:
    """Hard VRAM boundary before Wan 2.2 — required if InstantX/IP-Adapter ran."""
    import gc

    log.info(
        "VRAM flush before Wan (%s). InstantX=%s restart=%s — must be fully offloaded before I2V on 12GB.",
        reason,
        getattr(config, "ENABLE_INSTANTX", False),
        hard_restart or getattr(config, "RESTART_COMFY_BEFORE_WAN", False),
    )
    if getattr(config, "FORCE_GC_BEFORE_WAN", True):
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
    do_restart = bool(hard_restart or getattr(config, "RESTART_COMFY_BEFORE_WAN", False))
    if do_restart:
        wait = float(getattr(config, "COMFY_RESTART_WAIT_SEC", 90.0))
        for attempt in (1, 2):
            if restart_comfyui(wait_sec=wait):
                return
            log.warning(
                "ComfyUI restart attempt %s failed — waiting then retry", attempt
            )
            time.sleep(8)
            wait = max(wait, 120.0)
        log.warning("ComfyUI process restart failed twice — falling back to /free")
    free_comfyui_memory(unload_models=True, free_memory=True)


def _log_error(msg: str) -> None:
    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    with config.ERROR_LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")
    log.error(msg)


def _slug(text: str, limit: int = 40) -> str:
    """ASCII-safe filename slug (Devanagari etc. break ComfyUI / Windows paths)."""
    import hashlib
    import re

    keep = "".join(
        ch if ch.isascii() and (ch.isalnum() or ch in "-_") else "_" for ch in text.strip()
    )
    keep = re.sub(r"_+", "_", keep).strip("_")
    if len(keep) >= 6:
        return keep[:limit]
    return f"video_{hashlib.md5(text.encode('utf-8')).hexdigest()[:10]}"


def run_topic(job: TopicJob, *, dry_run: bool = False, client_id: str | None = None) -> Path | None:
    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cid = client_id or new_client_id()
    slug = _slug(job.topic)
    work = config.TEMP_DIR / slug
    work.mkdir(parents=True, exist_ok=True)

    log.info(
        "Director scripting: %s [%s/%s/%s/%s] director_mode=%s",
        job.topic,
        job.mode,
        job.ratio,
        job.lang,
        job.style,
        getattr(job, "director_mode", "story"),
    )
    if not dry_run:
        force_ollama_cpu()
        unload_ollama_gpu_models()
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

    raw_meta = dict(screenplay.raw or {})
    llm_off = bool(
        raw_meta.get("llm_disabled")
        or getattr(job, "director_mode", "story") == "raw"
        or raw_meta.get("reel_profile")
        in {
            "analog_phone_12s",
            "echo_chamber_12s",
            "raw_reel_12s",
            "usa_sports_quiz_12s",
            "music_video_lyric_180s",
        }
    )
    if llm_off:
        # Never let density rewriter invent poetic captions over locked overlay
        # (skip when caption_mode=per_beat/lyric_cues — distinct lines or timed lyrics)
        overlay = (raw_meta.get("text_overlay") or "").strip()
        if overlay and raw_meta.get("caption_mode") not in {"per_beat", "lyric_cues"}:
            from director import Scene as _Scene

            screenplay.scenes = [
                _Scene(
                    narration=overlay,
                    visual_prompt=s.visual_prompt,
                    motion_prompt=s.motion_prompt,
                    transition_to_next=s.transition_to_next,
                )
                for s in screenplay.scenes
            ]
        log.info("Raw/Reel mode: LLM bypass locked — overlay=%r", overlay or screenplay.scenes[0].narration)
    else:
        screenplay.scenes = _enforce_narration_density(screenplay.scenes, topic=job.topic)
    # Persist trinity + densified scenes for debugging
    raw_out = dict(screenplay.raw or {})
    raw_out.update(
        {
            "title": screenplay.title,
            "character_bible": screenplay.character_bible,
            "location_lock": screenplay.location_lock,
            "prop_bible": screenplay.prop_bible,
            "lighting_bible": screenplay.lighting_bible,
            "director_mode": getattr(job, "director_mode", "story"),
            "scenes": [
                {
                    "narration": s.narration,
                    "visual_prompt": s.visual_prompt,
                    "motion_prompt": s.motion_prompt,
                    "transition_to_next": s.transition_to_next,
                }
                for s in screenplay.scenes
            ],
        }
    )
    (work / "screenplay.json").write_text(
        __import__("json").dumps(raw_out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    width, height = config.RATIO_SIZES[job.ratio]
    wan_w, wan_h = config.WAN_SIZES.get(job.ratio, (480, 832))
    wan_length = config.WAN_LENGTH
    reel_profile = (screenplay.raw or {}).get("reel_profile")
    continuity_reel = _is_continuity_reel(job, screenplay)
    timed_reels = {
        "analog_phone_12s",
        "echo_chamber_12s",
        "raw_reel_12s",
        "wingsuit_15s",
        "wingsuit_oneshot_15s",
        "usa_sports_quiz_12s",
        "music_video_lyric_180s",
        "romance_love_120s",
    }
    beat_durations = list((screenplay.raw or {}).get("beat_durations") or [])
    if reel_profile in timed_reels:
        if beat_durations:
            config.SECONDS_PER_SCENE = float(beat_durations[0])
            wan_length = _wan_length_for_seconds(beat_durations[0])
        else:
            wan_length = int(getattr(config, "REEL_WAN_LENGTH", 96))
            config.SECONDS_PER_SCENE = float(getattr(config, "REEL_SECONDS_PER_SCENE", 6.0))
        log.info(
            "Timed Reel profile=%s beat0=%.1fs WAN_LENGTH=%s continuity_i2v=%s",
            reel_profile,
            float(beat_durations[0]) if beat_durations else config.SECONDS_PER_SCENE,
            wan_length,
            continuity_reel,
        )
    cinematic_suffix, negative_prompt = style_prompts(job.style)
    clip_paths: list[Path] = []
    narr_paths: list[Path] = []
    captions: list[str] = []
    character_ref: str | None = None
    master_still_local: Path | None = None
    prev_clip_local: Path | None = None

    flux_template = None
    wan_template = None
    single_template = None
    use_two_stage = False
    if not dry_run:
        config.refresh_workflow_paths()
        flux_wf = config.resolve_workflow_flux()
        wan_wf = config.resolve_workflow_wan()
        use_two_stage = bool(config.TWO_STAGE and flux_wf.exists() and wan_wf.exists())
        try:
            if use_two_stage:
                flux_template = load_workflow(flux_wf)
                wan_template = load_workflow(wan_wf)
                log.info(
                    "Two-stage mode: %s → %s (backend=%s)",
                    flux_wf.name,
                    wan_wf.name,
                    config.still_backend(),
                )
            else:
                single_template = load_workflow(wan_wf if wan_wf.exists() else None)
                log.info("Single-workflow mode: %s", wan_wf.name)
        except WorkflowNotFoundError as exc:
            _log_error(str(exc))
            return None

    overlay_caption = (raw_out.get("text_overlay") or "").strip()

    # Action: Flux suit bible before scenes — reject fantasy wings before any Wan work.
    _action_job = bool(
        (screenplay.raw or {}).get("action_flight")
        or (screenplay.raw or {}).get("reel_profile")
        in {"wingsuit_15s", "wingsuit_oneshot_15s"}
        or (screenplay.raw or {}).get("suit_bible")
    )
    if (
        (not dry_run)
        and use_two_stage
        and flux_template is not None
        and _action_job
        and bool((screenplay.raw or {}).get("suit_bible", True))
    ):
        n_bible = max(1, min(int(getattr(config, "ACTION_SUIT_BIBLE_CANDIDATES", 3) or 3), 6))
        bible_prompt = str(getattr(config, "ACTION_SUIT_BIBLE_PROMPT", "") or "").strip()
        if screenplay.character_bible:
            bible_prompt = (
                f"{bible_prompt}, CHARACTER: {screenplay.character_bible}"
                if bible_prompt
                else screenplay.character_bible
            )
        bible_neg = _scene_negative(
            negative_prompt, action_flight=True, is_fpv=False
        )
        best_bible = None
        best_bible_score = -1e9
        log.info("Suit bible: generating %s Flux plate(s) for fabric wing lock", n_bible)
        for bi in range(n_bible):
            if bi > 0:
                free_comfyui_memory(unload_models=True, free_memory=True)
                # /free can leave Comfy wedged on 12GB — ensure API is alive.
                try:
                    from utils import http_get_json

                    http_get_json(
                        f"http://{config.COMFYUI_HOST}/system_stats", timeout=8
                    )
                except Exception:
                    log.warning("Comfy unhealthy before suit bible %s — restarting", bi + 1)
                    restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 90)))
            # Must include "_still" so pick_best_output accepts PNG fallbacks.
            bprefix = f"dx_{slug}_suit_bible_still_c{bi}"
            bwf = apply_scene_to_workflow(
                flux_template,
                visual_prompt=bible_prompt,
                motion_prompt="",
                filename_prefix=bprefix,
                width=width,
                height=height,
                node_map=config.NODE_MAP_FLUX,
                include_motion_in_prompt=False,
                cinematic_suffix=cinematic_suffix,
                negative_prompt=bible_neg,
            )
            try:
                _bp, bouts = run_workflow(bwf, client_id=new_client_id())
            except (TimeoutError, Exception) as exc:
                log.error("Suit bible candidate %s failed: %s", bi + 1, exc)
                try:
                    restart_comfyui(wait_sec=float(getattr(config, "COMFY_RESTART_WAIT_SEC", 90)))
                except Exception:
                    pass
                continue
            bstill = pick_best_output(bouts, bprefix)
            if not bstill:
                log.warning("Suit bible candidate %s: no output", bi + 1)
                continue
            bscore = _score_suit_bible_still(bstill)
            log.info(
                "Suit bible candidate %s/%s score=%.3f file=%s",
                bi + 1,
                n_bible,
                bscore,
                bstill.name,
            )
            if best_bible is None or bscore > best_bible_score:
                best_bible = bstill
                best_bible_score = bscore
        if best_bible is not None:
            bible_local = work / f"suit_bible_{slug}.png"
            shutil.copy2(best_bible, bible_local)
            character_ref = stage_reference_image(bible_local, f"ref_{slug}.png")
            master_still_local = bible_local
            log.info(
                "Suit bible locked: %s score=%.3f → %s",
                bible_local.name,
                best_bible_score,
                character_ref,
            )
            free_comfyui_memory(unload_models=True, free_memory=True)

    for idx, scene in enumerate(screenplay.scenes):
        prefix = f"dx_{slug}_s{idx:02d}"
        log.info("Scene %s/%s", idx + 1, len(screenplay.scenes))

        vo_path = work / f"narration_{idx:02d}.wav"
        # Timed reels usually use beds / master audio; romance 120s still needs per-beat VO
        skip_tts = reel_profile in timed_reels and reel_profile != "romance_love_120s"
        if skip_tts:
            narr_paths.append(vo_path)
        else:
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

        captions.append(overlay_caption or scene.narration)

        # Per-beat Wan length for uneven reels (e.g. 8s + 3.9s)
        scene_wan_length = wan_length
        if beat_durations and idx < len(beat_durations):
            scene_wan_length = _wan_length_for_seconds(float(beat_durations[idx]))

        # Per-panel ratio (Echo Chamber split halves are 16:9)
        panel_specs = list((screenplay.raw or {}).get("panel_specs") or [])
        scene_ratio = job.ratio
        scene_face_fill = bool((screenplay.raw or {}).get("face_fill"))
        if idx < len(panel_specs) and isinstance(panel_specs[idx], dict):
            scene_ratio = str(panel_specs[idx].get("ratio") or scene_ratio)
            if "face_fill" in panel_specs[idx]:
                scene_face_fill = bool(panel_specs[idx].get("face_fill"))
        scene_w, scene_h = config.RATIO_SIZES.get(scene_ratio, (width, height))
        scene_wan_w, scene_wan_h = config.WAN_SIZES.get(scene_ratio, (wan_w, wan_h))
        # 12GB: length 128 @ 1024×576 leaves VRAM fragment → later Flux OOM. Cap + freeze-pad.
        hires_pixels = int(scene_wan_w) * int(scene_wan_h)
        if hires_pixels >= 1024 * 576:
            cap = int(getattr(config, "REEL_WAN_HIRES_LENGTH_CAP", 96))
            if scene_wan_length > cap:
                log.info(
                    "Scene %s hires Wan length capped %s→%s (freeze-pad to beat)",
                    idx + 1,
                    scene_wan_length,
                    cap,
                )
                scene_wan_length = cap
        _action_len = bool(
            (screenplay.raw or {}).get("action_flight")
            or (screenplay.raw or {}).get("reel_profile")
            in {"wingsuit_15s", "wingsuit_oneshot_15s"}
        )
        if _action_len:
            acap = int(getattr(config, "ACTION_WAN_LENGTH_CAP", 0) or 0)
            if acap and scene_wan_length > acap:
                log.info(
                    "Scene %s action Wan length capped %s→%s (freeze-pad to beat)",
                    idx + 1,
                    scene_wan_length,
                    acap,
                )
                scene_wan_length = acap
        # Music video: long chorus beats (20s+) OOM Wan@12GB — cap + MoviePy freeze-pad
        if reel_profile == "music_video_lyric_180s":
            mv_cap = int(getattr(config, "MUSIC_MV_WAN_LENGTH_CAP", 65) or 65)
            if scene_wan_length > mv_cap:
                log.info(
                    "Scene %s music-video Wan length capped %s→%s (freeze-pad to beat)",
                    idx + 1,
                    scene_wan_length,
                    mv_cap,
                )
                scene_wan_length = mv_cap
        # Romance 120s: long freeze-pad beats — keep Wan short on 12GB
        if reel_profile == "romance_love_120s":
            rom_cap = int(getattr(config, "ROMANCE_WAN_LENGTH_CAP", 81) or 81)
            if scene_wan_length > rom_cap:
                log.info(
                    "Scene %s romance Wan length capped %s→%s (freeze-pad to beat)",
                    idx + 1,
                    scene_wan_length,
                    rom_cap,
                )
                scene_wan_length = rom_cap
        if beat_durations and idx < len(beat_durations):
            log.info("Scene %s WAN_LENGTH=%s (%.1fs)", idx + 1, scene_wan_length, float(beat_durations[idx]))

        if dry_run:
            placeholder = work / f"{prefix}.mp4"
            dry_dur = (
                float(beat_durations[idx])
                if idx < len(beat_durations)
                else float(config.SECONDS_PER_SCENE)
            )
            _write_placeholder_clip(placeholder, scene_w, scene_h, dry_dur)
            clip_paths.append(placeholder)
            prev_clip_local = placeholder
            continue

        try:
            if use_two_stage:
                assert flux_template is not None and wan_template is not None
                n_scenes = len(screenplay.scenes)
                # Echo Chamber / face-fill reels: never apply Act-2/3 emotion bans
                # (reunion needs smiles; solo panels are already single-subject).
                _skip_act_emotion = bool(
                    (screenplay.raw or {}).get("compose_plan")
                    or (screenplay.raw or {}).get("face_fill")
                    or (screenplay.raw or {}).get("skip_act_emotion")
                    or (screenplay.raw or {}).get("action_flight")
                    or (screenplay.raw or {}).get("reel_profile")
                    in {
                        "echo_chamber_12s",
                        "wingsuit_15s",
                        "wingsuit_oneshot_15s",
                        "usa_sports_quiz_12s",
                        "music_video_lyric_180s",
                    }
                )
                is_act2 = (
                    (not continuity_reel)
                    and (not _skip_act_emotion)
                    and _is_act2_scene(idx, scene, n_scenes)
                )
                is_act3 = (
                    (not continuity_reel)
                    and (not _skip_act_emotion)
                    and _is_act3_scene(idx, scene, n_scenes)
                )
                use_prev_frame = bool(
                    continuity_reel and idx > 0 and prev_clip_local and prev_clip_local.exists()
                )

                if use_prev_frame:
                    # Anti-cut guardrail: Clip N starts from last frame of Clip N-1
                    still_local = work / f"{prefix}_cont_end.png"
                    if not _extract_frame(prev_clip_local, still_local, at_end=True):
                        _log_error(f"Continuity frame extract failed for {prefix}")
                        continue
                    start_name = stage_reference_image(still_local, f"{prefix}_start.png")
                    free_comfyui_memory(unload_models=True, free_memory=True)
                    log.info(
                        "Scene %s continuity I2V from last frame of %s",
                        idx + 1,
                        prev_clip_local.name,
                    )
                    _flush_before_wan(
                        reason=f"scene {idx + 1} continuity handoff",
                        hard_restart=_action_job
                        or getattr(config, "RESTART_COMFY_BEFORE_WAN", False),
                    )
                    unload_ollama_gpu_models()
                elif (
                    job.mode == "character"
                    and idx > 0
                    and master_still_local is not None
                    and bool(getattr(config, "CHARACTER_MASTER_STILL_LOCK", False))
                ):
                    log.warning(
                        "CHARACTER_MASTER_STILL_LOCK is ON — Scene %s will reuse Scene-1 plate "
                        "(breaks location changes). Prefer False + prompt identity lock.",
                        idx + 1,
                    )
                    still_local = master_still_local
                    start_name = stage_reference_image(still_local, f"{prefix}_start.png")
                    free_comfyui_memory(unload_models=True, free_memory=True)
                else:
                    # Stage A — Flux still (unique composition every scene)
                    flux_prompt = _scene_visual_for_flux(
                        scene,
                        idx=idx,
                        total=n_scenes,
                        screenplay=screenplay,
                        topic=job.topic,
                    )
                    if continuity_reel:
                        flux_prompt = _inject_reel_prop_lock(
                            flux_prompt,
                            continuity=True,
                            clock=(screenplay.raw or {}).get("reel_profile")
                            == "analog_phone_12s",
                        )
                    if scene_face_fill:
                        flux_prompt = _inject_face_fill(flux_prompt)
                    fpv_idxs = {
                        int(x) for x in ((screenplay.raw or {}).get("fpv_scene_indices") or [])
                    }
                    scene_is_fpv = idx in fpv_idxs
                    scene_neg = _scene_negative(
                        negative_prompt,
                        is_act2=is_act2,
                        is_act3=is_act3,
                        reel_continuity=continuity_reel,
                        face_fill=scene_face_fill,
                        action_flight=bool(
                            (screenplay.raw or {}).get("action_flight")
                            or (screenplay.raw or {}).get("reel_profile")
                            in {"wingsuit_15s", "wingsuit_oneshot_15s"}
                        ),
                        is_fpv=scene_is_fpv,
                        music_video=reel_profile == "music_video_lyric_180s",
                    )
                    if is_act2:
                        log.info(
                            "Act-2 isolation ON for scene %s (solo=%s, romance-positive banned)",
                            idx + 1,
                            getattr(config, "ACT2_ISOLATE_CHAR", "A"),
                        )
                    if is_act3:
                        log.info("Act-3 emotion lock ON for scene %s (smiling/happy banned)", idx + 1)
                    if idx == 0 and (screenplay.character_bible or screenplay.location_lock):
                        log.info(
                            "Dynamic Quad: char=%s | loc=%s | prop=%s | light=%s",
                            (screenplay.character_bible or "")[:60],
                            (screenplay.location_lock or "")[:60],
                            (screenplay.prop_bible or "")[:60],
                            (screenplay.lighting_bible or "")[:60],
                        )
                    if scene_ratio != job.ratio:
                        log.info(
                            "Scene %s panel ratio=%s Flux=%sx%s Wan=%sx%s face_fill=%s",
                            idx + 1,
                            scene_ratio,
                            scene_w,
                            scene_h,
                            scene_wan_w,
                            scene_wan_h,
                            scene_face_fill,
                        )
                    flux_ref = None
                    identity_lock = bool((screenplay.raw or {}).get("identity_lock_from_scene1"))
                    no_people = _is_no_people_scene(scene)
                    if (
                        (job.mode == "character" or identity_lock)
                        and character_ref
                        and (not no_people)
                    ):
                        flux_prompt = (
                            f"{flux_prompt}, same wingsuit flyer identity and suit colors "
                            f"as master reference, identical realistic fabric wingsuit every shot, "
                            f"NEW distinct camera angle for this beat"
                        )
                        if getattr(config, "REQUIRE_SCENE1_REF_LOCK", True) and config.NODE_MAP_FLUX.get(
                            "ipadapter_image"
                        ):
                            flux_ref = character_ref
                    if no_people:
                        log.info("Scene %s no-people cutaway: skip InstantX / identity inject", idx + 1)
                    # Race N seeds: FPV → chase-cam score; body action → suit DNA score.
                    if scene_is_fpv:
                        n_cands = int(getattr(config, "ACTION_FPV_STILL_CANDIDATES", 1) or 1)
                        score_fn = _score_fpv_still
                        score_tag = "fpv"
                    elif _action_job:
                        n_cands = int(getattr(config, "ACTION_SUIT_STILL_CANDIDATES", 1) or 1)
                        score_fn = _score_suit_bible_still
                        score_tag = "suit"
                    else:
                        n_cands = 1
                        score_fn = None
                        score_tag = ""
                    n_cands = max(1, min(n_cands, 8))
                    early_stop = float(getattr(config, "ACTION_FPV_SCORE_EARLY_STOP", 9e9) or 9e9)
                    best_still = None
                    best_score = -1e9
                    for cand_i in range(n_cands):
                        if cand_i > 0:
                            free_comfyui_memory(unload_models=True, free_memory=True)
                        cand_prefix = (
                            f"{prefix}_still_c{cand_i}" if n_cands > 1 else f"{prefix}_still"
                        )
                        flux_wf = apply_scene_to_workflow(
                            flux_template,
                            visual_prompt=flux_prompt,
                            motion_prompt="",
                            filename_prefix=cand_prefix,
                            width=scene_w,
                            height=scene_h,
                            reference_image_name=flux_ref,
                            node_map=config.NODE_MAP_FLUX,
                            include_motion_in_prompt=False,
                            cinematic_suffix=cinematic_suffix,
                            negative_prompt=scene_neg,
                        )
                        flux_outs: list = []
                        for flux_try in range(2):
                            try:
                                _pid, flux_outs = run_workflow(
                                    flux_wf,
                                    client_id=new_client_id()
                                    if (n_cands > 1 or flux_try > 0)
                                    else cid,
                                )
                                break
                            except (TimeoutError, RuntimeError, OSError) as exc:
                                log.error(
                                    "Flux candidate %s attempt %s/2 failed: %s",
                                    cand_i + 1,
                                    flux_try + 1,
                                    exc,
                                )
                                if flux_try == 0:
                                    restart_comfyui(
                                        wait_sec=float(
                                            getattr(config, "COMFY_RESTART_WAIT_SEC", 90.0)
                                        )
                                    )
                                    continue
                                flux_outs = []
                        if not flux_outs:
                            continue
                        still = pick_best_output(flux_outs, cand_prefix)
                        if not still:
                            continue
                        score = float(score_fn(still)) if score_fn and n_cands > 1 else 0.0
                        log.info(
                            "Scene %s Flux candidate %s/%s %sscore=%.3f file=%s",
                            idx + 1,
                            cand_i + 1,
                            n_cands,
                            f"{score_tag}_" if score_tag else "",
                            score,
                            still.name,
                        )
                        if best_still is None or score > best_score:
                            best_still = still
                            best_score = score
                        if scene_is_fpv and n_cands > 1 and best_score >= early_stop:
                            log.info(
                                "FPV early-stop: score %.3f >= %.3f after %s candidate(s)",
                                best_score,
                                early_stop,
                                cand_i + 1,
                            )
                            break
                    still = best_still
                    if not still:
                        _log_error(f"No Flux still for {prefix}")
                        continue
                    still_local = work / f"{prefix}_still.png"
                    shutil.copy2(still, still_local)
                    start_name = stage_reference_image(still_local, f"{prefix}_start.png")
                    extra = ""
                    if n_cands > 1 and score_tag:
                        extra = f" {score_tag}_score={best_score:.3f}"
                    log.info(
                        "Scene %s Flux still: %s (%s bytes)%s",
                        idx + 1,
                        still_local.name,
                        still_local.stat().st_size,
                        extra,
                    )
                    # Fallback identity lock only if suit bible did not run.
                    if (
                        (job.mode == "character" or identity_lock)
                        and (not scene_is_fpv)
                        and (not _is_no_people_scene(scene))
                        and (character_ref is None)
                    ):
                        character_ref = stage_reference_image(still_local, f"ref_{slug}.png")
                        master_still_local = still_local
                        log.info(
                            "Body-scene master character/identity lock saved: %s (scene %s)",
                            character_ref,
                            idx + 1,
                        )

                    # Music / romance hybrid: Ken Burns beats skip Wan (editor animates still).
                    beat_plan = list((screenplay.raw or {}).get("beat_plan") or [])
                    plan_i = beat_plan[idx] if idx < len(beat_plan) else {}
                    want_wan = True
                    if reel_profile == "music_video_lyric_180s" and beat_plan:
                        want_wan = bool(plan_i.get("wan")) or str(
                            plan_i.get("engine") or ""
                        ) == "wan"
                    if reel_profile == "romance_love_120s" and beat_plan:
                        eng = str(plan_i.get("engine") or "wan").lower()
                        want_wan = eng == "wan" or bool(plan_i.get("wan"))
                    if (
                        reel_profile in {"music_video_lyric_180s", "romance_love_120s"}
                        and beat_plan
                        and not want_wan
                    ):
                        kb_path = work / f"{prefix}_kb_still.png"
                        shutil.copy2(still_local, kb_path)
                        clip_paths.append(kb_path)
                        log.info(
                            "Scene %s Ken Burns still (skip Wan): %s",
                            idx + 1,
                            kb_path.name,
                        )
                        free_comfyui_memory(unload_models=True, free_memory=True)
                        continue

                    # Flush VRAM before Wan (12GB). Action/hires: full Comfy process restart.
                    _action = bool(
                        (screenplay.raw or {}).get("action_flight")
                        or (screenplay.raw or {}).get("reel_profile")
                        in {"wingsuit_15s", "wingsuit_oneshot_15s"}
                    )
                    _flush_before_wan(
                        reason=f"scene {idx + 1} post-Flux",
                        hard_restart=(
                            _action
                            or bool((screenplay.raw or {}).get("restart_comfy_before_wan"))
                            or getattr(config, "RESTART_COMFY_BEFORE_WAN", False)
                        ),
                    )
                    unload_ollama_gpu_models()

                # Stage B — Wan I2V from THAT scene's still / continuity frame
                wan_visual = _scene_visual_for_flux(
                    scene,
                    idx=idx,
                    total=n_scenes,
                    screenplay=screenplay,
                    topic=job.topic,
                )
                if continuity_reel:
                    wan_visual = _inject_reel_prop_lock(
                        wan_visual,
                        continuity=True,
                        clock=(screenplay.raw or {}).get("reel_profile")
                        == "analog_phone_12s",
                    )
                if scene_face_fill:
                    wan_visual = _inject_face_fill(wan_visual)
                wan_neg = _scene_negative(
                    negative_prompt,
                    is_act2=is_act2,
                    is_act3=is_act3,
                    reel_continuity=continuity_reel,
                    face_fill=scene_face_fill,
                    action_flight=bool(
                        (screenplay.raw or {}).get("action_flight")
                        or (screenplay.raw or {}).get("reel_profile")
                            in {"wingsuit_15s", "wingsuit_oneshot_15s"}
                    ),
                    is_fpv=idx
                    in {int(x) for x in ((screenplay.raw or {}).get("fpv_scene_indices") or [])},
                    music_video=reel_profile == "music_video_lyric_180s",
                )
                _mv = reel_profile == "music_video_lyric_180s"
                _rom = reel_profile == "romance_love_120s"
                _require_wan = bool((screenplay.raw or {}).get("require_wan")) or _rom
                _wan_retry = _action_job or _mv or _rom
                best = None
                wan_outs: list = []
                from pipeline_wan import render_scene_wan_two_pass, should_use_two_pass

                if should_use_two_pass():
                    if still_local and Path(still_local).exists():
                        still_path = Path(still_local)
                    elif start_name:
                        still_path = config.COMFYUI_INPUT / start_name
                        if not still_path.exists():
                            raise RuntimeError(
                                f"Scene {idx + 1}: staged still missing for two-pass Wan: {still_path}"
                            )
                    else:
                        raise RuntimeError(f"Scene {idx + 1}: no still for two-pass Wan")
                    seed = 1000 + idx * 17
                    try:
                        best = render_scene_wan_two_pass(
                            still=still_path,
                            visual=wan_visual,
                            motion=scene.motion_prompt or "",
                            prefix=prefix,
                            seed=seed,
                            neg=wan_neg,
                            ww=scene_wan_w,
                            wh=scene_wan_h,
                            length=scene_wan_length,
                            work=work,
                        )
                        wan_outs = [best]
                        log.info(
                            "Scene %s two-pass Wan OK: %s (%s bytes)",
                            idx + 1,
                            best.name,
                            best.stat().st_size,
                        )
                    except Exception as wan_exc:
                        log.error(
                            "Two-pass Wan failed for scene %s: %s",
                            idx + 1,
                            wan_exc,
                        )
                        if not getattr(config, "QUALITY_ALLOW_KEN_BURNS_FALLBACK", False):
                            raise
                        if (
                            (_mv or _rom)
                            and still_local
                            and Path(still_local).exists()
                        ):
                            kb_path = work / f"{prefix}_kb_still.png"
                            shutil.copy2(still_local, kb_path)
                            clip_paths.append(kb_path)
                            log.warning(
                                "Scene %s two-pass Wan failed — Ken Burns fallback: %s",
                                idx + 1,
                                kb_path.name,
                            )
                            wan_outs = []
                            free_comfyui_memory(unload_models=True, free_memory=True)
                            continue
                        raise
                else:
                    wan_wf = apply_scene_to_workflow(
                        wan_template,
                        visual_prompt=wan_visual,
                        motion_prompt=scene.motion_prompt,
                        filename_prefix=prefix,
                        width=scene_wan_w,
                        height=scene_wan_h,
                        reference_image_name=start_name,
                        node_map=config.NODE_MAP_WAN,
                        cinematic_suffix=cinematic_suffix,
                        negative_prompt=wan_neg,
                    )
                    if config.NODE_MAP_WAN.get("width"):
                        _set_input(wan_wf, config.NODE_MAP_WAN["width"], "length", scene_wan_length)
                    if _action_job:
                        q_steps = int(getattr(config, "WAN_QUALITY_STEPS", 0) or 0)
                        if q_steps >= 16:
                            _bump_wan_sampler_steps(wan_wf, q_steps)
                            log.info("Wan quality steps=%s for action scene %s", q_steps, idx + 1)
                    for wan_try in range(3 if _rom else (2 if _wan_retry else 1)):
                        try:
                            _pid2, wan_outs = run_workflow(
                                wan_wf, client_id=new_client_id() if wan_try else cid
                            )
                            break
                        except (TimeoutError, RuntimeError, OSError) as wan_exc:
                            tries = 3 if _rom else (2 if _wan_retry else 1)
                            log.error(
                                "Wan attempt %s/%s failed for scene %s: %s",
                                wan_try + 1,
                                tries,
                                idx + 1,
                                wan_exc,
                            )
                            if wan_try + 1 < tries and _wan_retry:
                                restart_comfyui(
                                    wait_sec=float(
                                        getattr(config, "COMFY_RESTART_WAIT_SEC", 120.0)
                                    )
                                )
                                continue
                            if (
                                (not _require_wan)
                                and (_mv or _rom)
                                and still_local
                                and Path(still_local).exists()
                            ):
                                kb_path = work / f"{prefix}_kb_still.png"
                                shutil.copy2(still_local, kb_path)
                                clip_paths.append(kb_path)
                                log.warning(
                                    "Scene %s Wan failed — Ken Burns fallback: %s",
                                    idx + 1,
                                    kb_path.name,
                                )
                                wan_outs = []
                                break
                            raise
                    if (_mv or _rom) and not wan_outs:
                        if _require_wan:
                            raise RuntimeError(
                                f"Scene {idx + 1}: require_wan=True but Wan produced no output"
                            )
                        free_comfyui_memory(unload_models=True, free_memory=True)
                        continue
                    # Never reuse stale ComfyUI mp4s from prior runs (silent soft 480×832 trap)
                    best = pick_best_output(wan_outs, prefix, allow_stale_disk=False)
                # Comfy OOM often returns empty outs without raising — KB fallback
                if (_mv or _rom) and not best:
                    if _require_wan:
                        raise RuntimeError(
                            f"Scene {idx + 1}: require_wan=True but Wan output missing"
                        )
                    still_fb = None
                    if still_local and Path(still_local).exists():
                        still_fb = Path(still_local)
                    else:
                        cand = work / f"{prefix}_still.png"
                        if cand.exists():
                            still_fb = cand
                    if still_fb is not None:
                        kb_path = work / f"{prefix}_kb_still.png"
                        shutil.copy2(still_fb, kb_path)
                        clip_paths.append(kb_path)
                        log.warning(
                            "Scene %s Wan empty/OOM — Ken Burns fallback: %s",
                            idx + 1,
                            kb_path.name,
                        )
                        free_comfyui_memory(unload_models=True, free_memory=True)
                        continue
                free_comfyui_memory(unload_models=True, free_memory=True)
            else:
                assert single_template is not None
                n_scenes = len(screenplay.scenes)
                _skip_act_emotion = bool(
                    (screenplay.raw or {}).get("compose_plan")
                    or (screenplay.raw or {}).get("face_fill")
                    or (screenplay.raw or {}).get("skip_act_emotion")
                    or (screenplay.raw or {}).get("action_flight")
                    or (screenplay.raw or {}).get("reel_profile")
                    in {
                        "echo_chamber_12s",
                        "wingsuit_15s",
                        "wingsuit_oneshot_15s",
                        "usa_sports_quiz_12s",
                        "music_video_lyric_180s",
                    }
                )
                is_act2 = (
                    (not continuity_reel)
                    and (not _skip_act_emotion)
                    and _is_act2_scene(idx, scene, n_scenes)
                )
                is_act3 = (
                    (not continuity_reel)
                    and (not _skip_act_emotion)
                    and _is_act3_scene(idx, scene, n_scenes)
                )
                single_visual = _scene_visual_for_flux(
                    scene,
                    idx=idx,
                    total=n_scenes,
                    screenplay=screenplay,
                    topic=job.topic,
                )
                if continuity_reel:
                    single_visual = _inject_reel_prop_lock(
                        single_visual,
                        continuity=True,
                        clock=(screenplay.raw or {}).get("reel_profile")
                        == "analog_phone_12s",
                    )
                single_neg = _scene_negative(
                    negative_prompt,
                    is_act2=is_act2,
                    is_act3=is_act3,
                    reel_continuity=continuity_reel,
                )
                wf = apply_scene_to_workflow(
                    single_template,
                    visual_prompt=single_visual,
                    motion_prompt=scene.motion_prompt,
                    filename_prefix=prefix,
                    width=width,
                    height=height,
                    reference_image_name=character_ref if job.mode == "character" else None,
                    node_map=config.NODE_MAP,
                    cinematic_suffix=cinematic_suffix,
                    negative_prompt=single_neg,
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
            if best.suffix.lower() not in {".mp4", ".webm", ".mkv", ".mov", ".gif"}:
                if (
                    reel_profile in {"music_video_lyric_180s", "romance_love_120s"}
                    and best.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                ):
                    local_still = work / f"{prefix}_kb_still{best.suffix.lower()}"
                    if Path(best) != local_still:
                        shutil.copy2(best, local_still)
                    else:
                        local_still = Path(best)
                    clip_paths.append(local_still)
                    log.info("Scene %s still plate for Ken Burns: %s", idx + 1, local_still.name)
                    continue
                _log_error(f"Skipping non-video ComfyUI output for {prefix}: {best.name}")
                continue
            local = work / best.name
            shutil.copy2(best, local)
            clip_paths.append(local)
            prev_clip_local = local
        except Exception as exc:  # noqa: BLE001
            _log_error(f"ComfyUI scene {idx} failed: {exc}\n{traceback.format_exc()}")
            continue

    if not clip_paths:
        _log_error(f"No clips produced for: {job.topic}")
        return None

    if len(clip_paths) < len(screenplay.scenes):
        _log_error(
            f"Incomplete continuity render: {len(clip_paths)}/{len(screenplay.scenes)} clips for {job.topic}"
        )
        log.error("Expected one Wan clip per scene — check ComfyUI errors above")
        compose_plan = (screenplay.raw or {}).get("compose_plan") or []
        reel_profile = (screenplay.raw or {}).get("reel_profile") or ""
        # Never ship a half-Reel (stale panels / missing reunion)
        if compose_plan or reel_profile in timed_reels or continuity_reel:
            needed = set(range(len(screenplay.scenes)))
            for step in compose_plan:
                needed.update(int(x) for x in (step.get("sources") or []))
            _log_error(
                f"Compose/reel requires {len(screenplay.scenes)} clips "
                f"(indices {sorted(needed)}) but only have {len(clip_paths)} — aborting assemble"
            )
            return None

    transitions = [s.transition_to_next for s in screenplay.scenes[: len(clip_paths)]]
    log.info(
        "Assembling %s clips with transitions=%s",
        len(clip_paths),
        transitions,
    )
    for i, p in enumerate(clip_paths):
        log.info("  clip[%s]=%s (%s bytes)", i, p.name, p.stat().st_size if p.exists() else 0)

    out_file = config.OUTPUT_DIR / f"{slug}.mp4"
    try:
        burn = True
        if (screenplay.raw or {}).get("burn_captions") is False:
            burn = False
        if getattr(config, "FORCE_NO_CAPTIONS", False):
            burn = False
            log.info("FORCE_NO_CAPTIONS: skipping text overlay burn")
        # PyCaps permanently disabled — MoviePy TextClip burn only
        assemble_video(
            clip_paths,
            narr_paths,
            out_path=out_file,
            ratio=job.ratio,
            burn_captions=burn,
            caption_lines=(captions[: len(clip_paths)] if burn else None),
            transitions=transitions,
            screenplay_meta=dict(screenplay.raw or {}),
        )
        log.info("Wrote %s", out_file)
        from pipeline_wan import write_quality_run_report

        write_quality_run_report(work)
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


def _extract_frame(video_path: Path, out_png: Path, *, at_end: bool = False) -> bool:
    try:
        from moviepy.editor import VideoFileClip

        clip = VideoFileClip(str(video_path))
        if at_end:
            fps = float(clip.fps or config.FPS or 24)
            t = max(0.0, float(clip.duration) - (1.0 / max(fps, 1.0)))
        else:
            t = min(0.1, max(clip.duration / 2, 0))
        clip.save_frame(str(out_png), t=t)
        clip.close()
        return out_png.exists()
    except Exception:  # noqa: BLE001
        return False
