# Quality OS Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make DirectorX’s default local path match max practical cinematic quality on RTX 5070 12GB: two-pass Wan always, steps≥14, HQ 1080 upscale, no freeze-pad on quality profiles, then IP-Adapter/LoRA identity.

**Architecture:** `QUALITY_FIRST` config drives pipeline/editor; Wan via `scripts/wan_two_pass_moe.two_pass_wan`; upscale via sleep317-class ffmpeg chain; P1+ weights optional with loud fallbacks.

**Tech Stack:** Python, ComfyUI GGUF, `wan_two_pass_moe`, MoviePy/ffmpeg, pytest.

**Design:** `docs/plans/2026-08-05-quality-os-upgrade-design.md`  
**Audit:** `docs/plans/2026-08-05-pipeline-quality-audit.md`  
**Rule:** `.cursor/rules/quality-first-cinematic.mdc`

---

### Task 1: QUALITY_FIRST config knobs

**Files:**
- Modify: `config.py`
- Create: `tests/test_quality_os_config.py`

**Step 1: Failing test**

```python
import config

def test_quality_first_defaults():
    assert getattr(config, "QUALITY_FIRST", False) is True
    assert int(config.WAN_QUALITY_STEPS) >= 14
    assert float(getattr(config, "WAN_QUALITY_CFG", 0)) >= 4.0
    assert int(config.FLUX_STEPS) >= 24
    assert getattr(config, "QUALITY_ALLOW_KEN_BURNS_FALLBACK", True) is False
    assert getattr(config, "QUALITY_ALLOW_FREEZE_PAD", True) is False
```

**Step 2: Run — expect FAIL**

**Step 3: Add to `config.py`**

```python
QUALITY_FIRST = True
WAN_QUALITY_STEPS = 14          # was ineffective at <16 for action-only bump
WAN_QUALITY_CFG = 4.5
FLUX_STEPS = 24                 # was 22
QUALITY_ALLOW_KEN_BURNS_FALLBACK = False
QUALITY_ALLOW_FREEZE_PAD = False
EXPORT_UPSCALE_HQ_CHAIN = True  # sleep317-class eq+unsharp+noise
CINE_GRAIN_STRENGTH = 0.015     # softer on upscaled 480 sources (was 0.028)
```

Keep `WAN_SIZES` at 480; do not enable 512 by default.

**Step 4: PASS**

**Step 5: Commit only if user asked**

---

### Task 2: HQ upscale chain in editor

**Files:**
- Modify: `editor.py` (`_ffmpeg_upscale`)
- Create: `tests/test_quality_os_upscale.py`

**Step 1: Failing test** — monkeypatch subprocess; when `EXPORT_UPSCALE_HQ_CHAIN=True`, assert vf string contains `eq=` and `unsharp=` and `noise=`.

**Step 2: Replace `_ffmpeg_upscale` body** with sleep317-class chain when flag on:

```python
vf = f"scale={out_w}:{out_h}:flags=lanczos"
if getattr(config, "EXPORT_UPSCALE_HQ_CHAIN", False):
    vf = (
        f"{vf},"
        f"eq=contrast=1.08:brightness=-0.02:saturation=0.92:gamma=0.95,"
        f"unsharp=3:3:0.55:3:3:0.0,"
        f"noise=alls=6:allf=t"
    )
elif getattr(config, "EXPORT_UPSCALE_UNSHARP", False):
    vf = f"{vf},unsharp=5:5:0.6:5:5:0.0"
```

Preserve audio copy behavior of current function.

**Step 3: PASS**

---

### Task 3: Disable freeze-pad when QUALITY_FIRST

**Files:**
- Modify: `editor.py` (`_fit_clip_to_duration`, callers in `assemble_video`)
- Create/extend: `tests/test_quality_os_freeze_pad.py`

**Step 1: Test** — with `QUALITY_ALLOW_FREEZE_PAD=False`, short clip + longer target → trim-only or raise/log + no ImageClip freeze append (prefer: if clip shorter than target by >0.15s, log warning and **do not** pad; leave short — stitch uses real motion only).

**Step 2: Implement**

```python
def _fit_clip_to_duration(clip, target: float):
    ...
    if pad > 0.05:
        if not getattr(config, "QUALITY_ALLOW_FREEZE_PAD", True):
            log.warning("freeze-pad suppressed (QUALITY_FIRST); leaving duration %.2fs < target %.2fs", clip.duration, target)
            return clip
        # existing freeze path
```

Same guard in `_ffmpeg_fit_duration` if it freeze-pads.

**Step 3: PASS**

---

### Task 4: Pipeline helper — render Wan via two_pass

**Files:**
- Create: `pipeline_wan.py` (or `director_wan.py`) thin wrapper
- Modify: `pipeline.py` Wan section (~1380–1475)
- Create: `tests/test_quality_os_two_pass_router.py`

**Step 1: Unit test router**

```python
from pipeline_wan import should_use_two_pass, wan_quality_steps, wan_quality_cfg

def test_two_pass_default():
    assert should_use_two_pass() is True
    assert wan_quality_steps() >= 14
    assert wan_quality_cfg() >= 4.0
```

**Step 2: Implement wrapper**

```python
# pipeline_wan.py
def should_use_two_pass() -> bool:
    return bool(getattr(config, "QUALITY_FIRST", True))

def render_scene_wan_two_pass(*, still: Path, visual, motion, prefix, seed, neg, ww, wh, length, work: Path) -> Path:
    from wan_two_pass_moe import two_pass_wan  # scripts on path
    out = work / f"{prefix}_twopass.mp4"
    two_pass_wan(
        still, visual=visual, motion=motion, prefix=prefix, seed=seed, neg=neg,
        out_mp4=out, ww=ww, wh=wh, length=length,
        steps=wan_quality_steps(), cfg=wan_quality_cfg(),
    )
    return out
```

Ensure `sys.path` includes `scripts/` like premium renderers.

**Step 3: In `pipeline.py`**, when `should_use_two_pass()`:
- Skip building single-process `wan_wf` / `run_workflow` for Wan
- Call `render_scene_wan_two_pass(...)` with `still_local`, prompts, `scene_wan_w/h`, `scene_wan_length`
- On failure: if `QUALITY_ALLOW_KEN_BURNS_FALLBACK` is False → **raise** (even for music/romance); else keep old KB path

**Step 4: Unit test** monkeypatch `two_pass_wan` to touch outfile; assert pipeline helper returns path.

**Step 5: PASS**

---

### Task 5: Flux steps already 24 — verify apply path

**Files:**
- Modify: `tests/test_quality_os_config.py` (extend)
- Verify: `comfy_runner.apply_scene_to_workflow` still sets Flux steps from `FLUX_STEPS`

**Step 1:** Test that still graph gets `FLUX_STEPS` ≥ 24 when QUALITY_FIRST.

**Step 2:** Fix only if wiring broken.

---

### Task 6: run_report stub for quality path

**Files:**
- Modify: `pipeline.py` end of successful assemble (or `utils.py`)
- Create: `tests/test_quality_os_report.py`

Write `temp/<job>/quality_run_report.json`:

```json
{
  "quality_first": true,
  "wan_path": "two_pass_moe",
  "wan_steps": 14,
  "wan_cfg": 4.5,
  "flux_steps": 24,
  "upscale": "hq_chain",
  "freeze_pad": false,
  "ken_burns_fallback": false
}
```

---

### Task 7: Regression tests for existing quality guards

**Files:**
- Run: `pytest tests/test_quality_fixes.py tests/test_quality_os_*.py -v`

Fix any breakage from grain/freeze-pad changes (update expectations if tests asserted old grain 0.028).

---

### Task 8 (P1): Weights download + preflight

**Files:**
- Create: `scripts/download_quality_os_weights.ps1`
- Create: `cinema_master/preflight.py` (or `quality_os/preflight.py`)
- Create: `assets/cinema/INSTALL_WEIGHTS.md`

Download checklist:
- Real-ESRGAN x2plus/x4plus → `C:\ComfyUI\models\upscale_models\`
- Flux IP-Adapter + CLIP vision → ipadapter / clip_vision dirs

Preflight returns missing list; does not block P0.

---

### Task 9 (P1): Flux IP-Adapter workflow wire

**Files:**
- Create: `workflows/flux_t2i_ipadapter_gguf_api.json` + node map
- Modify: `comfy_runner.py` / `config.NODE_MAP_FLUX` when weights present
- Test: map non-null `ipadapter_image` when preflight ok

---

### Task 10 (P2): Character LoRA train + A/B proof

**Files:**
- Create: `scripts/gen_character_bible_stills.py` (12–15 Flux stills, fixed identity prompt)
- Create: `scripts/train_character_lora.md` + trainer invoke (ai-toolkit / kohya — pick what fits 12GB)
- Create: `scripts/render_quality_ab_proof.py` + `scripts/run_quality_ab_proof_external.bat`
- External A/B: same prompts, LoRA off vs on → `final_outputs/Quality_AB_*.mp4`

---

## Dependency order

```
T1 config → T2 upscale → T3 freeze-pad
T1 → T4 two-pass pipeline → T5 flux verify → T6 report → T7 pytest
T8 → T9 (P1)
T10 (P2)
```

## Verification before “done” (P0)

1. `pytest tests/test_quality_os_*.py tests/test_quality_fixes.py -v` PASS  
2. Code review: pipeline Wan path calls `two_pass_wan` when `QUALITY_FIRST`  
3. Optional external smoke: 1 scene two-pass + HQ 1080 (user-approved long run)  

## Out of scope this plan

Wan 720 default, cloud Wan 2.6, deleting Q4 models, CrewAI.
