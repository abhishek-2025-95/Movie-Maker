# B-Roll Lyric Music Video — Design

**Status:** Approved  
**Profile:** `music_video_broll_lyric_180s`

## Locked

- Full ~180s · 16:9 · `FINAL_HIT_SONG.wav`
- Picture: **Pexels/Pixabay free B-roll only** (no Flux/Wan faces)
- Lyrics: **PyCaps** + `assets/captions/cinematic_premium.css` (karaoke gold word + effects)
- Timings: SunoX `lyric_alignment.json` / whisper words

## Section → B-roll queries

| Section | Query vibe |
|---------|------------|
| Intro | rainy city window night bokeh |
| Verse 1 | dark kitchen night phone coffee |
| Hallway | apartment hallway night |
| Empty bed | empty bed streetlight blinds night |
| Pre/Chorus | city skyline night rain fire escape |
| Train | subway metro train night interior |
| Bridge | rainy sidewalk streetlights night |
| Outro | window city lights night hopeful |

## Pipeline

1. Download 1–2 clips per section (16:9 prefer)  
2. Fit/crop to 1920×1080, cut to beat durations  
3. Stitch + mux master song  
4. PyCaps burn with premium CSS + word karaoke  
5. Export `final_outputs/music_video_broll_lyric_*.mp4`
