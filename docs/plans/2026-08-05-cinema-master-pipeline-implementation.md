# Cinema Master Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship a story-agnostic `cinema_master` package that runs Flux+IP-Adapter → hybrid Wan 480/720 → stitch → Real-ESRGAN 1080 + face restore → Edge-TTS/music/Foley → grade/grain 24fps master on RTX 5070 12GB.

**Architecture:** New package under repo root `cinema_master/` with stage modules + CLI. Reuses `comfy_runner`, `wan_two_pass_moe`, `voice.synthesize`, `utils.apply_cinematic_layering`. Stories only supply beat JSON.

**Tech Stack:** Python 3, ComfyUI API, ComfyUI_IPAdapter_plus, ComfyUI-GGUF, Wan 2.2 MoE two-pass, Real-ESRGAN, MoviePy/ffmpeg, edge-tts, numpy Foley, pytest.

**Design:** `docs/plans/2026-08-05-cinema-master-pipeline-design.md`

---

### Task 1: Package skeleton + beat schema

**Files:**
- Create: `cinema_master/__init__.py`
- Create: `cinema_master/schema.py`
- Create: `tests/test_cinema_master_schema.py`
- Create: `assets/cinema/beats_smoke.json` (fixture: 1 close + 1 wide)

**Step 1: Write the failing test**

```python
# tests/test_cinema_master_schema.py
from cinema_master.schema import Beat, load_beats, ShotTag

def test_load_smoke_beats():
    beats = load_beats("assets/cinema/beats_smoke.json")
    assert len(beats) == 2
    assert beats[0].shot_tag == ShotTag.CLOSE
    assert beats[1].shot_tag == ShotTag.WIDE

def test_rejects_missing_shot_tag(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"title":"x","aspect":"16:9","beats":[{"id":"a","prompt":"p","motion":"m"}]}', encoding="utf-8")
    try:
        load_beats(p)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "shot_tag" in str(e).lower()
```

**Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cinema_master_schema.py -v`  
Expected: FAIL (module not found)

**Step 3: Minimal implementation**

- `ShotTag` enum: `close` | `wide`
- `Beat` dataclass: `id`, `shot_tag`, `prompt`, `motion`, `duration_hint` (float, default 5.0), `audio_cues` (list[str], default []), `plate` (optional str), `transition` (`hard`|`xfade`, default hard for wide/threat cues)
- `BeatSheet`: `title`, `aspect` (`16:9`|`9:16`), `beats`, optional `vo_text`, `seed`
- `load_beats(path) -> BeatSheet`
- Smoke JSON with two beats

**Step 4: Run tests — expect PASS**

**Step 5: Commit** (only if user asked)

```bash
git add cinema_master tests/test_cinema_master_schema.py assets/cinema/beats_smoke.json
git commit -m "feat(cinema_master): add beat schema and smoke fixture"
```

---

### Task 2: Resolution router (close 480 / wide 720)

**Files:**
- Create: `cinema_master/sizing.py`
- Create: `tests/test_cinema_master_sizing.py`
- Modify: `config.py` — add `CINEMA_MASTER_*` constants

**Step 1: Failing test**

```python
from cinema_master.sizing import wan_size_for_shot, master_size_for_aspect
from cinema_master.schema import ShotTag

def test_close_is_480_landscape():
    assert wan_size_for_shot(ShotTag.CLOSE, "16:9") == (832, 480)

def test_wide_prefers_720_landscape():
    assert wan_size_for_shot(ShotTag.WIDE, "16:9", prefer_720=True) == (1280, 720)

def test_wide_fallback_480():
    assert wan_size_for_shot(ShotTag.WIDE, "16:9", prefer_720=False) == (832, 480)

def test_master_1080():
    assert master_size_for_aspect("16:9") == (1920, 1080)
    assert master_size_for_aspect("9:16") == (1080, 1920)
```

**Step 2: Run — expect FAIL**

**Step 3: Implement**

```python
# cinema_master/sizing.py
WAN_CLOSE = {"16:9": (832, 480), "9:16": (480, 832)}
WAN_WIDE = {"16:9": (1280, 720), "9:16": (720, 1280)}
MASTER = {"16:9": (1920, 1080), "9:16": (1080, 1920)}

def wan_size_for_shot(shot_tag, aspect, *, prefer_720=True):
    if shot_tag.value == "wide" and prefer_720:
        return WAN_WIDE[aspect]
    return WAN_CLOSE[aspect]
```

Config knobs:

```python
CINEMA_MASTER_TRY_720 = True
CINEMA_MASTER_WAN_STEPS = 14
CINEMA_MASTER_EXPORT_BITRATE = "15000k"
CINEMA_MASTER_REQUIRE_IPADAPTER = True
CINEMA_MASTER_REQUIRE_AUDIO = False
```

**Step 4: PASS + commit if requested**

---

### Task 3: Weights / nodes preflight checklist

**Files:**
- Create: `cinema_master/preflight.py`
- Create: `assets/cinema/INSTALL_WEIGHTS.md`
- Create: `tests/test_cinema_master_preflight.py`
- Create: `scripts/download_cinema_master_weights.ps1`

**Step 1: Failing test**

```python
from cinema_master.preflight import check_cinema_master, PreflightResult

def test_preflight_returns_structured_result(monkeypatch):
    # Force missing weight → ok False when require_ipadapter
    r = check_cinema_master(require_ipadapter=True, require_upscale=True)
    assert isinstance(r, PreflightResult)
    assert hasattr(r, "missing")
    assert hasattr(r, "ok")
```

**Step 2: Implement checklist**

Required paths (document exact HF filenames in INSTALL_WEIGHTS.md):

| Asset | Expected location |
|-------|-------------------|
| IP-Adapter Flux | `C:\ComfyUI\models\ipadapter\` (Flux IP-Adapter .safetensors) |
| CLIP Vision | `C:\ComfyUI\models\clip_vision\` |
| Real-ESRGAN | `C:\ComfyUI\models\upscale_models\RealESRGAN_x4plus.pth` (or x2plus) |
| Face restore | `C:\ComfyUI\models\facerestore_models\` or GFPGAN path used by script |
| Existing | Flux Q5 GGUF, Wan 2.2 Q4 high/low, ae, umt5, wan VAE |
| Node | `ComfyUI_IPAdapter_plus` present |

`check_cinema_master()` returns `PreflightResult(ok, missing: list[str], notes: list[str])`.  
Hard-fail policy enforced later in `run.py` when `CINEMA_MASTER_REQUIRE_IPADAPTER`.

**Step 3: PowerShell downloader** with HuggingFace URLs for IP-Adapter Flux + RealESRGAN + face model (user runs manually).

**Step 4: PASS + commit if requested**

---

### Task 4: Flux + IP-Adapter bible workflow

**Files:**
- Create: `workflows/flux_t2i_ipadapter_gguf_api.json` (or export from Comfy after manual graph)
- Create: `workflows/node_map_flux_ipadapter_gguf.json`
- Create: `cinema_master/bible.py`
- Create: `tests/test_cinema_master_bible.py` (unit: apply wiring / mock; skip live GPU)

**Step 1:** Manually (or script) build Comfy graph:

`UnetLoaderGGUF(flux Q5) + DualCLIP + AE + LoadImage(ref) + IPAdapterAdvanced + KSampler + SaveImage`

Export API JSON into `workflows/`.

**Step 2: Node map**

```json
{
  "positive_prompt": "...",
  "negative_prompt": "...",
  "ksampler_seed": "...",
  "width": "...",
  "height": "...",
  "save_prefix": "...",
  "ipadapter_image": "<LoadImage node id>"
}
```

**Step 3: `bible.py` API**

```python
def ensure_weights_or_raise(): ...
def generate_hero_plate(*, prompt, neg, seed, aspect, ref_image: Path | None, work: Path) -> Path
def generate_shot_plate(*, hero: Path, prompt, seed, shot_tag, work: Path) -> Path
```

- First call may generate hero without ref (or from optional user ref).
- Later shots pass hero into IP-Adapter LoadImage.
- Still sizes: 16:9 → 1344×768; 9:16 → 768×1344.

**Step 4: Unit test** mocks `run_workflow` / asserts `reference_image_name` set when hero exists.

**Step 5: Commit if requested**

---

### Task 5: Motion stage (Wan hybrid + fallback)

**Files:**
- Create: `cinema_master/motion.py`
- Create: `tests/test_cinema_master_motion.py`
- Reuse: `scripts/wan_two_pass_moe.py` (`two_pass_wan`)

**Step 1: Failing test for fallback logic**

```python
from cinema_master.motion import resolve_wan_attempt_plan
from cinema_master.schema import ShotTag

def test_close_single_attempt():
    plan = resolve_wan_attempt_plan(ShotTag.CLOSE, "16:9")
    assert plan == [(832, 480)]

def test_wide_try_720_then_480():
    plan = resolve_wan_attempt_plan(ShotTag.WIDE, "16:9")
    assert plan == [(1280, 720), (832, 480)]
```

**Step 2: Implement `render_beat_motion(...)`**

- For each size in plan: call `two_pass_wan` with `WAN_QUALITY_STEPS` / `CINEMA_MASTER_WAN_STEPS`
- On OOM / Comfy error containing VRAM/oom: restart Comfy once, try next size
- Write chunk path + `meta.json` `{width,height,fallback: bool}`
- Length: clamp `duration_hint` to Wan length 65–81 frames @ 16fps

**Step 3: PASS unit tests; live smoke deferred to Task 10**

---

### Task 6: Stitch

**Files:**
- Create: `cinema_master/stitch.py`
- Create: `tests/test_cinema_master_stitch.py`

**Step 1:** Test with two tiny solid-color mp4 fixtures (ffmpeg-generated in test setup).

**Step 2:** Implement:

- `hard` concat demuxer
- `xfade` only when `transition==xfade` and duration ≥ 0.25s
- Output `edit/rough.mp4` silent

Reuse patterns from `scripts/render_victorian_forbidden_love_v2.py` stitch helpers where possible (extract shared util if copy >30 lines).

---

### Task 7: Upscale + face restore

**Files:**
- Create: `cinema_master/upscale.py`
- Create: `tests/test_cinema_master_upscale.py`

**Step 1:** Prefer ffmpeg+Real-ESRGAN CLI *or* Comfy upscale workflow if node available.

Practical 12GB path (v1):

1. Extract frames or use `realesrgan-ncnn-vulkan` / `ffmpeg` with model if installed  
2. Fallback chain documented in INSTALL_WEIGHTS.md:  
   - Best: Real-ESRGAN x2/x4 to master size  
   - Fallback (only if `require_upscale=False`): lanczos + unsharp (log WARNING — not cinema default)

**Step 2:** Face restore: port `_face_detail_restore` idea from `scripts/render_wan_dinner_scene_pro.py` (blend toward hero still on face region) **or** GFPGAN/CodeFormer if weights present.

**Step 3:** Unit test: synthetic 160×90 clip → assert output size 1920×1080 when master is 16:9 (may use lanczos in test monkeypatch).

**API:**

```python
def upscale_to_master(src: Path, dest: Path, *, aspect: str, hero_still: Path | None) -> Path
```

---

### Task 8: Audio (Edge-TTS + local music + Foley)

**Files:**
- Create: `cinema_master/audio.py`
- Create: `tests/test_cinema_master_audio.py`
- Reuse: `voice.synthesize`

**Step 1: Foley**

Map `audio_cues` tokens → procedural numpy beds (reuse Victorian/dinner patterns):

- `room`, `door`, `strings`, `wind`, `footsteps`, `silence`

**Step 2: Music**

v1 local music gen = **procedural score** (layered soft pads/strings via numpy/scipy or simple oscillators with musical intervals) — no cloud. Optional: if `assets/cinema/music_bed.wav` exists, prefer file.

**Step 3: VO**

If `vo_text` set → `voice.synthesize` (edge-tts path) ducked under music.

**Step 4: Mix** to `edit/mix.wav` matching rough duration.

**Step 5:** Unit test generates ≤1s mix without Comfy.

---

### Task 9: Master encode

**Files:**
- Create: `cinema_master/master.py`
- Create: `tests/test_cinema_master_master.py`
- Reuse: `utils.apply_cinematic_layering`

**Step 1:** Combine 1080 video + mix → apply grain/vignette/gamma → write `final_outputs/<title>_cinema_master.mp4` at 24fps, `CINEMA_MASTER_EXPORT_BITRATE`, yuv420p.

**Step 2:** Write `run_report.json`:

```json
{
  "title": "...",
  "flux": "flux1-dev-Q5_K_S.gguf",
  "wan": ["wan2.2_i2v_high_noise_14B_Q4_K_M.gguf", "wan2.2_i2v_low_noise_14B_Q4_K_M.gguf"],
  "ipadapter": true,
  "beats": [{"id": "b0", "wan_wh": [1280, 720], "fallback": false}],
  "audio": {"vo": true, "music": "procedural", "foley": ["room", "door"]}
}
```

---

### Task 10: Orchestrator + external launcher + smoke

**Files:**
- Create: `cinema_master/run.py`
- Create: `scripts/run_cinema_master_smoke_external.bat`
- Create: `scripts/run_cinema_master_external.bat`
- Create: `assets/cinema/beats_smoke.json` (finalize)

**CLI:**

```text
python -m cinema_master.run --beats assets/cinema/beats_smoke.json --run-id smoke1
python -m cinema_master.run --beats path/to/story.json --run-id <id> [--require-audio]
```

**Flow in `run.py`:**

1. preflight (hard fail missing IP-Adapter/upscale when flags on)  
2. bible plates  
3. motion per beat  
4. stitch  
5. upscale  
6. audio  
7. master  
8. print final path + report path  

**Bat:** `start "CinemaMaster" cmd /k` pattern like Victorian external bats — never Cursor-tied.

**Live smoke (user machine, external):** 1 close + 1 wide beat, expect either 720 success or logged fallback_480, final 1080 mp4.

---

### Task 11: Wire config refresh + docs pointer

**Files:**
- Modify: `config.py` — cinema_master constants + optional workflow path helpers
- Modify: `docs/plans/2026-08-05-cinema-master-pipeline-design.md` — add “Implemented by …” link once plan file exists
- Create: `assets/cinema/beats_example_victorian.json` (consumer stub only — not required to render in this plan)

---

## Dependency order

```
Task1 schema → Task2 sizing → Task3 preflight
                ↘ Task4 bible
Task2 → Task5 motion → Task6 stitch → Task7 upscale
Task8 audio (parallel with 6–7)
Task9 master ← 7+8
Task10 run ← all
Task11 config/docs
```

## Verification (before claiming done)

1. `pytest tests/test_cinema_master_*.py -v` all PASS  
2. Preflight fails loudly if IP-Adapter weights missing  
3. External smoke produces `*_cinema_master.mp4` @ 1920×1080 + `run_report.json` proving Wan 2.2 + IP-Adapter  
4. No sine-only final audio  

## Out of scope (do not implement in this plan)

CrewAI, InstantID custom node, Wan Q5/Q6 swap, RIFE, full Victorian remaster (that is first **consumer** after pipeline green).
