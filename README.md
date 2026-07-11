# DirectorX

Local, hands-off **cinematic AI video factory** for your RTX 5070.

`topics.txt` → Ollama screenplay → ComfyUI (Flux → Wan 2.2 I2V) → voice → MoviePy → `final_outputs/`

## What you already have

- RTX 5070 (12GB)
- Ollama models (`llama3.1:8b`, `deepseek-r1:8b`, …)
- ComfyUI at `C:\ComfyUI` with **Wan 2.2 I2V FP8**

## Quick start

```powershell
cd C:\Users\user\Documents\DirectorX
powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1
.\.venv\Scripts\Activate.ps1
python main.py --dry-run
```

Dry-run validates the orchestrator with placeholder clips + TTS (no ComfyUI needed).

## Production path (best quality)

1. `powershell -ExecutionPolicy Bypass -File .\scripts\install_comfy_nodes.ps1`
2. Download Flux FP8/GGUF + encoders (see `scripts/download_models.md`)
3. Build Flux→Wan graph in ComfyUI, export **API Format** → `workflow_api.json` in this folder
4. Map node IDs in `config.py` (`NODE_MAP`)
5. Optional: `pip install TTS` + put `assets/voices/default.wav`
6. Edit `topics.txt`, start ComfyUI + Ollama, then:

```powershell
python main.py
```

## Topic format

```
plain topic uses defaults (faceless, 9:16, en)
mode:character ratio:16:9 lang:en | A detective in neon rain
mode:faceless ratio:9:16 lang:hi | अगर पृथ्वी रुक जाए
```

## Honest quality note

This stack can produce **top-tier automated cinematic shorts** when the Comfy graph and prompts are solid. Fully hands-off does not magically equal a human-graded Netflix finale every time — the factory maximizes quality; your exported workflow is the ceiling.
