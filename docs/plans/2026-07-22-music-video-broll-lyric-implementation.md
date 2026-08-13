# B-Roll Lyric MV — Implementation

**Script:** `scripts/build_broll_lyric_mv.py`  
**Output:** `final_outputs/music_video_broll_lyric_I_Never_Said_It_Out.mp4`

## Steps

1. Download curated Mixkit free B-roll (window/kitchen/apartment/bedroom/city/rain/subway/neon)
2. Cover-crop to 1920×1080, loop if short, stitch to 180s
3. Mux `FINAL_HIT_SONG.wav`
4. Convert `lyric_alignment.json` karaoke → whisper_json segments
5. Burn **ASS karaoke** (gold active word, Arial Black, spaced lyrics) — reliable premium look
6. Optional: PyCaps `hype` template (custom CSS path was illegible with Pictex)

## Run

```powershell
python scripts/build_broll_lyric_mv.py
```

## Deliverable

- 1920×1080 · 180s · ~296 MB
- No AI faces — Mixkit B-roll only
- Timed karaoke from SunoX alignment
