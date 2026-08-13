# DirectorX Pipeline Quality Audit (post US 10s)

**Date:** 2026-08-13  
**Hardware:** RTX 5070 12GB · Flux Q5 GGUF · Wan 2.2 Q4 MoE two-pass  
**Trigger:** `US_Brooklyn_Stoop_Almost_10s.mp4` machine-PASS / look-FAIL (“AI shaky”, random)  
**Mandate:** Quality over time — no proof shortcuts  

## Verdict

The 10s job already runs the **max-quality technical path this box has wired** (Flux 24 → IP-Adapter → Wan two-pass 14 / CFG 4.5 @ 832×480 → Real-ESRGAN 1920×1080 → real bed). Specs can PASS while the film still feels random and synthetic.

Two different gaps:

1. **Direction** — no theme, no prop spine, no readable story object. “Pretty couple almost-kisses on a stoop” is a cliché **and** a Wan failure class.
2. **Pixels** — 12GB Wan is native 480p Q4 at 16fps. Upscale + fps conform **sharpen the artifacts** (hair boil, skin crawl, stitch ghosts). Analyzer checks files, not faces.

Honest ceiling is unchanged: watchable cinematic **short**, not theatrical 1080 motion. Prompt-only identity is not lock.

## What already shipped (do not re-diagnose as missing)

| Piece | Status on the 10s job |
|-------|------------------------|
| Two-pass Wan MoE | Used (`scripts/wan_two_pass_moe.py`) |
| Wan steps ≥14, CFG ~4.5 | Locked |
| Flux ≥22–25 | 24 |
| Hero-plate lock | One two-shot; v2 continues from last frame |
| IP-Adapter | Used when weights exist |
| Real-ESRGAN 1080 | Used when `RealESRGAN_x2plus.pth` + spandrel exist |
| Freeze-pad / Ken Burns | Forbidden on this job |
| External terminal | `.bat` / tmux launchers |
| QC report | ffprobe + 5 frames + `quality_run_report.json` |

v1 look-fail was **not** “forgot two-pass”. It was crop-jump xfade (tight crop → ghost double face), kiss/push-in/wind-in-hair motion, and a generic prompt.

## Gap A — Direction (why it feels random)

The factory can generate **footage**. It cannot yet generate a **film** unless a human hardcodes one.

- No **prop bible**. US indie shorts that land in 10s hang on one object (porch light, umbrella, ring, letter). v1 had hydrangeas as garnish.
- No **theme line**. “Almost kiss” is a beat, not a meaning. Maximum effect needs a sentence the viewer can repeat: *waiting is a kind of love*.
- **Shot grammar fights Wan.** Cheek-to-cheek, camera push-in, wind in afro, face contact = morph/smear class. Locked-off + air gap + hands-on-stoop is the 12GB grammar.
- Default `director.py` love path is still **120s Mumbai rain** (8 beats, freeze-pad caps in `pipeline.py`). The US 10s piece is a one-off script, not the factory default.
- `cinema_master/` was designed 2026-08-05 and **never landed**. Every story re-implements Flux/Wan/stitch/upscale/audio. Quality therefore depends on which script you ran, not on a shared master.
- Audio is a competent procedural piano bed, not a cue tied to a motif (lamp hum, wait, pay-off line).
- Still-QC (`scripts/still_qc.py`) only rejects blank/gray Flux collapse. It does not check “is the lantern in frame?” or “are there two faces?”

**Fix in this revision:** lock the 10s job to **The Porch Light** — yellow lantern always in frame, locked-off, no kiss, end line *She never turns it off.*

## Gap B — Pixels (why PASS still looks AI-shaky)

Impact order on *this* hardware:

1. **Wan native 480p Q4** — faces are ~80–110 px tall. Real-ESRGAN ×2 then lanczos to 1080 invents pores and **hair/skin crawl**. Sharper ≠ more real.
2. **16fps → 24fps without RIFE** — ffmpeg `fps=24` duplicates frames. Motion stutters; people read it as “AI shaky”. P3 in Quality OS, not built.
3. **Geometry mismatch at the stitch** — v1 xfade from a **tight crop** of the hero onto beat 0 = double exposure at ~5s. v2 continues from last frame. Any remaining 0.125s xfade can still ghost if Wan drifted.
4. **Motion the model cannot hold** — lean-in, push-in, wind, lips approaching. Identity fight + smear. v2 forbids these; the concept must not re-ask for them.
5. **No temporal consistency / optical-flow lock** — each Wan beat is a new 81-frame denoise. Continue-from-last-frame is the only lock.
6. **No face gate before Wan** — a hero still with a beard, extra person, or missing lamp still goes to a 10–20 min two-pass. Analyzer `pass: true` if the file is 1080/10s/stereo.
7. **No face restore after ESR** — cinema_master design called GFPGAN/CodeFormer; not wired. Plastic Flux skin stays plastic, then gets sharpened.
8. **Grade + grain on 480** — HQ ffmpeg fallback uses `unsharp` + `noise=alls=6`. On upscaled Q4 this is crawl, not film grain. ESR path is cleaner; fallback is not.
9. **Identity stack is incomplete** — IP-Adapter without a **character LoRA for this couple**. Existing P2 LoRA is `ar_filter_viewer` only. Flux ignored “white clean-shaven man” on v1 and drew a Black bearded man. Cast must match what Flux actually paints, then LoRA-lock it.
10. **Main factory still social/reel** — `pipeline.py` still **caps Wan length and freeze-pads** on romance_120s / music / action / hires. Quality OS P0 two-pass is on when `QUALITY_FIRST`, but duration cheating remains on the default director path.
11. **Ops** — Comfy is a git checkout + system Python 3.11, not portable. `huggingface-hub` vs transformers already crashed a healthy GPU night. No lockfile for the Comfy env.

## What “best quality” cannot mean here

Do not sell:

- Theatrical 1080p native motion on 12GB Q4 Wan
- Prompt-only race/beard/face lock
- Kiss / push-in / wind-in-hair as “cinematic”
- Analyzer PASS as picture PASS
- `cinema_master` as if it exists in the repo

Do sell:

- 10s locked-off US short with one motif, two-pass Wan, 1080 master, real bed
- Identity that matches the hero plate, continued last-frame to last-frame
- Honest next ROI (below), local only

## Max-quality ROI (local only, after this concept lock)

| Rank | Change | Why |
|------|--------|-----|
| 1 | Concept + prop + shot grammar (this job) | Biggest “random” fix; also avoids Wan failure class |
| 2 | Still-QC beyond blank: lamp hotspot + two-face sanity before Wan | Stops 20 min renders on a bad hero |
| 3 | RIFE (or similar) 16→24 | Largest remaining motion jitter |
| 4 | Skin-safe upscale: ESR ×2 then lanczos; **no** unsharp/noise on faces | Cuts hair/skin crawl |
| 5 | Face restore after ESR (CodeFormer/GFPGAN) | Plastic skin |
| 6 | Character LoRA for this cast (bible from accepted hero) | Real identity lock |
| 7 | Land `cinema_master` as the only 16:9 path | Stops one-off script quality drift |
| 8 | Kill freeze-pad caps in `pipeline.py` via chunk plans | Factory 120s is still reel-tier |
| 9 | Optional Wan Q5 / 720 wide probe (two-pass only) | Extra detail if VRAM holds |
| 10 | Comfy env lock (`huggingface-hub`, torch, custom nodes) | Stops silent launch rot |

## This 10s revision (The Porch Light)

- **Theme:** waiting is a kind of love  
- **Prop spine:** yellow porch lantern, always ON, same place in frame  
- **Grammar:** locked-off tripod, six-inch air gap, hands on stoop, no kiss / push-in / wind  
- **Payoff line:** *She never turns it off.*  
- **Same pixels path:** two-pass 14 / CFG 4.5, last-frame continue, Real-ESRGAN 1080, new work dir so v1/v2 cache is not reused  

Do not call it cinematic-done until new ffprobe + `qc_frames` exist on the user’s 5070.
