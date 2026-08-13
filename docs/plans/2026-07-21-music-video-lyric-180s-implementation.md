# Music Video Lyric 180s Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a full ~180s 16:9 cinematic lyric music video for `FINAL_HIT_SONG.wav` using hybrid Flux stills + Ken Burns + Wan-on-peaks, with all timed lyric cues burned and the original song as master audio.

**Architecture:** New locked reel profile `music_video_lyric_180s` in `director.py` drives 12 story plates. Pipeline generates Flux stills for all plates and Wan only for beats marked `engine=wan`. Editor Ken-Burns stills to beat durations, stitches to 180s, muxes the song WAV, and burns cues from `lyric_alignment.json`.

**Tech Stack:** DirectorX (Python), Flux FP8 via ComfyUI, Wan 2.2 I2V @ 16:9 832×480, MoviePy assemble, existing SunoX lyric alignment JSON.

**Design:** `docs/plans/2026-07-21-music-video-lyric-180s-design.md`

---

### Task 1: Failing tests — screenplay lock

**Files:**
- Create: `tests/test_music_video_lyric_reel.py`
- Modify: `director.py` (later)

**Step 1: Write the failing test**

```python
from director import TopicJob, generate_screenplay

def test_music_video_lyric_locked_screenplay():
    job = TopicJob(
        topic="music video lyric I Never Said It Out Loud FINAL_HIT_SONG",
        director_mode="story",
        ratio="16:9",
        lang="en",
    )
    sp = generate_screenplay(job)
    assert sp.raw.get("reel_profile") == "music_video_lyric_180s"
    assert sp.raw.get("llm_disabled") is True
    assert sp.raw.get("skip_character_bible") is True
    assert sp.raw.get("burn_captions") is True
    assert sp.raw.get("caption_mode") == "lyric_cues"
    assert sp.raw.get("master_audio")  # path or marker
    assert sp.raw.get("target_duration_sec") == 180.0
    assert len(sp.scenes) == 12
    engines = [s.get("engine") if isinstance(s, dict) else None for s in (sp.raw.get("beat_plan") or [])]
    assert "wan" in engines and "ken_burns" in engines
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_music_video_lyric_reel.py::test_music_video_lyric_locked_screenplay -v`  
Expected: FAIL (profile not found)

**Step 3: Commit** (after Task 2 turns it green — see Task 2)

---

### Task 2: Locked screenplay + topic detect

**Files:**
- Modify: `director.py` — add `_is_music_video_lyric_topic`, `_fallback_music_video_lyric`
- Modify: `main.py` — skip Ollama for this topic
- Test: `tests/test_music_video_lyric_reel.py`

**Step 1: Implement topic detect**

Match if topic contains (`music video` or `lyric mv` or `FINAL_HIT_SONG`) and romantic/confession cues optional; also match explicit `music_video_lyric_180s`.

**Step 2: Implement `_fallback_music_video_lyric(job)`**

Return `Screenplay` with 12 `Scene`s matching design beat sheet. `raw` must include:

```python
{
  "reel_profile": "music_video_lyric_180s",
  "narrative_engine": "music_video_lyric_180s",
  "llm_disabled": True,
  "skip_act_emotion": True,
  "skip_character_bible": True,
  "burn_captions": True,
  "caption_mode": "lyric_cues",
  "caption_position": "bottom",
  "continuity_i2v": False,
  "restart_comfy_before_wan": True,
  "target_duration_sec": 180.0,
  "loop_end_sec": 180.0,
  "master_audio": r"C:\Users\user\Documents\SunoX\workspace\FINAL_HIT_SONG.wav",
  "lyric_alignment": r"C:\Users\user\Documents\SunoX\workspace\lyric_alignment.json",
  "beat_durations": [...],  # 12 floats summing ~180
  "beat_plan": [
    {"engine": "ken_burns", "wan": False},
    # ... wan=True on beats 5,6,9,10,11,12 (0-index: 4,5,8,9,10,11)
  ],
  "cinematic_grade": "music_soft",  # lower grain than default
}
```

Apartment `location_lock` / `prop_bible` / `lighting_bible` as in design. Empty `character_bible`.

**Step 3: Hook** in `generate_screenplay` and `_build_raw_screenplay` before generic fallbacks.

**Step 4: `main.py` `_job_needs_ollama`** return False for `_is_music_video_lyric_topic`.

**Step 5: Run tests**

Run: `pytest tests/test_music_video_lyric_reel.py -v`  
Expected: PASS

**Step 6: Commit** (only if user asks)

---

### Task 3: Lyric cue loader + Ken Burns helper

**Files:**
- Modify: `utils.py` — `load_lyric_cues(path) -> list[dict]`, `ken_burns_clip(still_path, duration, w, h)`
- Test: `tests/test_music_video_lyric_reel.py`

**Step 1: Failing tests**

```python
def test_load_lyric_cues():
    from utils import load_lyric_cues
    cues = load_lyric_cues(r"C:\Users\user\Documents\SunoX\workspace\lyric_alignment.json")
    assert len(cues) >= 40
    assert cues[0]["text"]
    assert cues[0]["end"] > cues[0]["start"]

def test_ken_burns_duration(tmp_path):
    from utils import ken_burns_clip
    from PIL import Image
    p = tmp_path / "s.png"
    Image.new("RGB", (1344, 768), (20, 30, 40)).save(p)
    clip = ken_burns_clip(p, duration=5.0, out_w=1920, out_h=1080)
    assert abs(float(clip.duration) - 5.0) < 0.05
    clip.close()
```

**Step 2: Implement**

- `load_lyric_cues`: read JSON `cues[]` → `{start,end,text,section}`  
- `ken_burns_clip`: ImageClip → slow zoom 1.0→1.06 (or pan), resize/crop to out size, set duration

**Step 3: pytest pass**

---

### Task 4: Pipeline — timed reel + selective Wan

**Files:**
- Modify: `pipeline.py`
  - Add `music_video_lyric_180s` to `timed_reels` / skip_act / skip_char sets
  - When `beat_plan[i].engine == "ken_burns"`: skip Wan; copy still → write a still-marked clip path (or `.png` that editor will KB)
  - When `engine == "wan"`: existing Flux→Wan path; on Wan failure log + fall back to still
  - Do not synthesize TTS for this profile
  - Pass `master_audio` / `lyric_alignment` through `screenplay_meta`

**Step 1: Test** that `_scene_visual_for_flux` for music video has no trench-coat bible (reuse quiz pattern with `skip_character_bible`).

**Step 2: Implement selective Wan + still output paths.**

Convention: for KB beats, `clip_paths` may be PNG stills; editor detects image vs video.

**Step 3: Smoke dry-run**

Run: `python main.py --dry-run --mode story --topic-file topics_music_video_lyric.txt --scenes 12 -v`  
Expected: placeholder assemble path or screenplay dump without Comfy.

---

### Task 5: Editor — assemble + master audio + lyric burn

**Files:**
- Modify: `editor.py`
  - Add profile to timed reel sets
  - If clip is image: `ken_burns_clip(...)` to beat duration
  - After stitch: if `meta["master_audio"]` exists → `video.set_audio(AudioFileClip(master).subclip(0, min(180, dur)))`
  - If `caption_mode == "lyric_cues"`: load cues; for each cue, overlay TextClip on the *stitched* timeline at absolute start/end (not per-beat caption_lines)
  - Soft grade: if `cinematic_grade == "music_soft"`, reduce grain/vignette vs default

**Step 1: Unit-test lyric overlay scheduling** (pure function preferred):

```python
def test_cues_to_overlays_window():
    from editor import _lyric_cues_in_window
    cues = [{"start": 1.0, "end": 3.0, "text": "Hello"}, {"start": 10.0, "end": 12.0, "text": "World"}]
    mid = _lyric_cues_in_window(cues, t0=0.0, t1=5.0)
    assert len(mid) == 1 and mid[0]["text"] == "Hello"
```

(Or burn on full timeline once — simpler: one CompositeVideoClip of all cue overlays on final video.)

**Step 2: Implement full-timeline lyric burn** (preferred): after stitch, before export, composite all cue TextClips with `set_start(cue.start)`.

**Step 3: Manual dry-run check captions don't use single `text_overlay` flatten.**

---

### Task 6: Topic file + config knobs

**Files:**
- Create: `topics_music_video_lyric.txt`
- Modify: `config.py` (optional): `MUSIC_MV_GRAIN`, `MUSIC_MV_VIGNETTE` soft defaults

**Content of topic file:**

```
music video lyric I Never Said It Out Loud FINAL_HIT_SONG 16:9
```

---

### Task 7: End-to-end render

**Steps:**
1. Restart ComfyUI healthy  
2. Run:  
   `python main.py --mode story --scenes 12 -v --topic-file topics_music_video_lyric.txt`  
   (no `--no-captions`)  
3. Verify output under `final_outputs/`:
   - duration ≈ 180s  
   - 1920×1080  
   - audio is the song  
   - lyrics visible on chorus line ~57s  

**Fallback:** If overnight Wan unstable, set all `beat_plan` engines to `ken_burns` for a still-led lyric MV (still valid deliverable).

---

### Task 8: Verification checklist

- [ ] `pytest tests/test_music_video_lyric_reel.py -v` green  
- [ ] No CHARACTER_BIBLE / trench coat in Flux prompts  
- [ ] Master audio = FINAL_HIT_SONG.wav  
- [ ] ≥40 lyric burns present in assemble logs  
- [ ] Wan used only on peak beats (or documented KB fallback)

---

## Execution handoff

Plan complete and saved to `docs/plans/2026-07-21-music-video-lyric-180s-implementation.md`.

**Two execution options:**

1. **Subagent-Driven (this session)** — fresh subagent per task, review between tasks  
2. **Parallel Session (separate)** — new session with executing-plans, batch with checkpoints  

Which approach?
