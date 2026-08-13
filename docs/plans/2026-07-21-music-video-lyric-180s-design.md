# Music Video — *I Never Said It Out Loud* (Lyric MV)

**Status:** v2 rendering (distinct locations + identity lock)  
**Profile:** `music_video_lyric_180s`  
**Audio:** `C:\Users\user\Documents\SunoX\workspace\FINAL_HIT_SONG.wav` (~180.08s, 44.1kHz stereo)  
**Lyrics sync:** `C:\Users\user\Documents\SunoX\workspace\lyric_alignment.json` (~44 cues)

## Locked choices

| Choice | Value |
|--------|--------|
| Length | Full song ~3:00 |
| Aspect | 16:9 (YouTube) |
| Lyrics | Full timed burn (all cues) |
| Approach | Hybrid: Flux stills + Ken Burns + Wan on peaks |

## Song brief

Late-night confession ballad-pop. Soft intimate male lead, warm keys/guitar, gentle 808/clap (~74 BPM bedroom-pop feel). Hook: *I never said it out loud*. Arc: quiet almost-love → chorus lift → bridge resolve → said-out-loud outro.

## World & character

- **World:** One late-night city apartment — blue phone/kitchen light, streetlight gold on empty bed, wet window bokeh, hoodie on hallway chair.
- **Protagonist:** Solitary young man; over-shoulder / reflection-heavy; avoid hard face close-ups across cuts.
- **Forbidden:** Default romance duo character bible; stadium/crowd spectacle; TTS narration.

## Beat sheet

| # | Time | Section | Visual | Engine |
|---|------|---------|--------|--------|
| 1 | 0:00–0:07 | Intro | City lights through window glass | Ken Burns |
| 2 | 0:07–0:21 | Verse 1a | Kitchen, blue phone glow | Ken Burns |
| 3 | 0:21–0:35 | Verse 1b | Hoodie on chair; cold coffee | Ken Burns |
| 4 | 0:35–0:50 | Verse 1c | Quiet bedroom / almost-memory | KB → light Wan |
| 5 | 0:50–0:57 | Pre-chorus 1 | Over-shoulder before confession | Wan |
| 6 | 0:57–1:19 | Chorus 1 | Window/city reflection lift | Wan + KB hold |
| 7 | 1:22–1:40 | Verse 2a | Streetlight on empty bed | Ken Burns |
| 8 | 1:40–1:58 | Verse 2b | Late train reflection; headphones | Ken Burns |
| 9 | 1:58–2:05 | Pre-chorus 2 | Draft/delete confession on phone | Wan |
| 10 | 2:05–2:27 | Chorus 2 | Doorway almost-stayed | Wan + KB |
| 11 | 2:29–2:44 | Bridge | Decisive stillness / resolve | Wan |
| 12 | 2:44–3:00 | Final + outro | Clear voice; city blur; hope | Wan → KB settle |

## Pipeline

1. Ingest WAV + lyric alignment JSON  
2. Locked screenplay (`music_video_lyric_180s`) — 12 plates, apartment bible, `skip_character_bible`  
3. Flux FP8 stills @ 16:9 (~1344×768) for all plates  
4. Wan 480 only on peak beats (~5–6); else MoviePy Ken Burns  
5. Assemble to 180s; **mux original song as sole audio**  
6. Burn all lyric cues (lower-third, soft stroke)  
7. Export lanczos → 1920×1080, high bitrate; light grade (low grain)

## Quality / risk

- Best full-song look on 12GB OSS (Flux FP8 → Wan 480); not Veo/Netflix grade.
- Wan failures fall back to Ken Burns on that plate.
- Comfy hard-restart between Wan jobs.
- Expected render window: ~2–4 hours typical.

## Success criteria

- [ ] Full ~180s 16:9 MP4 with original song in sync  
- [ ] All lyric cues burned and readable  
- [ ] Apartment world continuity (same night DNA)  
- [ ] Chorus/bridge beats have real Wan motion  
- [ ] No TTS / no romance-duo bible leakage  
