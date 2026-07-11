# Local Cinematic Video Factory — Design

**Date:** 2026-07-12  
**Project:** DirectorX (`local_video_bot`)  
**Hardware:** AMD Ryzen 7 9800X3D, NVIDIA RTX 5070 (12GB VRAM)  
**ComfyUI:** `C:\ComfyUI` (Wan 2.2 I2V FP8 already present)

## Goal

Hands-off local pipeline: drop topics → get high-volume cinematic MP4s with zero API fees. Support faceless + character modes, 9:16 + 16:9, English + Hindi, XTTS voice cloning.

## Quality reality

Open-source Flux + Wan 2.2 can match or beat many paid web tools on fidelity when the I2V graph, prompts, and assembly are solid. Fully automated output will not always equal a human-directed Netflix edit; the system maximizes quality via I2V anchoring, cinematic prompt expansion, character lock (IP-Adapter), and clean assembly.

## Architecture

```
topics.txt
    → Director (Ollama JSON screenplay)
    → ComfyUI API (Flux still → Wan I2V → optional upscale)
    → XTTS v2 (cloned narration)
    → MoviePy (stitch, duck music, burn captions)
    → final_outputs/*.mp4
```

### Topic line format

```
mode:faceless|character ratio:9:16|16:9 lang:en|hi | Topic text here
```

Defaults: `faceless`, `9:16`, `en`.

### Modules

| Module | Role |
|--------|------|
| `config.py` | Paths, Ollama model, ComfyUI host, durations, node ID map |
| `utils.py` | ComfyUI HTTP queue + WebSocket wait |
| `director.py` | Ollama → strict JSON scenes (`narration`, `visual_prompt`, `motion_prompt`) |
| `comfy_runner.py` | Load `workflow_api.json`, inject prompts/seeds/prefix, run jobs |
| `voice.py` | XTTS clone from `assets/voices/default.wav` |
| `editor.py` | Concat clips, attach VO, optional BGM ducking, captions |
| `main.py` | Batch loop over topics |
| `scripts/setup_*.ps1` | Custom nodes, model download checklist, stub workflow |

### Character mode

Scene 0 generates a reference still. Later scenes pass that image into IP-Adapter (when node mapped in config). Faceless mode skips reference lock.

### VRAM strategy (12GB)

- Flux FP8 / GGUF for stills  
- Wan 2.2 I2V 14B FP8 (already on disk)  
- Sequential stages (unload between heavy steps when possible)  
- Target ~5s clips @ 480p/720p generation, upscale after

### Failure handling

- Skip topic on Ollama/ComfyUI failure, log to `temp/errors.log`  
- Continue batch  
- Require ComfyUI + Ollama reachable before start

## Non-goals (v1)

- Cloud APIs  
- GUI dashboard  
- Auto-upload to YouTube  
- Guaranteeing perfect face consistency without a tuned Comfy graph

## Success criteria

1. `python main.py` processes `topics.txt` end-to-end when deps are running  
2. Per-topic mode/ratio/lang honored  
3. Outputs land in `final_outputs/`  
4. Setup scripts document/install missing Flux + custom nodes
