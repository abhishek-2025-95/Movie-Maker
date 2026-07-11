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

1. `powershell -ExecutionPolicy Bypass -File .\scripts\install_comfy_nodes.ps1` *(already run)*
2. Download Flux + Wan LoRAs:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\download_flux.ps1
```

3. API workflows are pre-built (`workflows/flux_t2i_api.json`, `workflows/wan_i2v_api.json`) with `NODE_MAP_*` wired in `config.py`. Re-generate anytime with `python scripts\build_workflow_api.py`.
4. Optional: `pip install TTS` + put `assets/voices/default.wav`
5. Start **ComfyUI** + **Ollama**, edit `topics.txt`, then:

```powershell
python main.py
```

Two-stage (default): **Flux still → Wan 2.2 I2V → MoviePy**.

## Topic format

```
plain topic uses defaults (faceless, 9:16, en)
mode:character ratio:16:9 lang:en | A detective in neon rain
mode:faceless ratio:9:16 lang:hi | अगर पृथ्वी रुक जाए
```

## Honest quality note

This stack can produce **top-tier automated cinematic shorts** when the Comfy graph and prompts are solid. Fully hands-off does not magically equal a human-graded Netflix finale every time — the factory maximizes quality; your exported workflow is the ceiling.
