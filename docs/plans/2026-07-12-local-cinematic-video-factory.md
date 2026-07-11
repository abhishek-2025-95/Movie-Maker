# Local Cinematic Video Factory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a hands-off local cinematic video factory (Ollama → ComfyUI Flux/Wan → XTTS → MoviePy) optimized for RTX 5070.

**Architecture:** Modular Python orchestrator with topic metadata, ComfyUI API/WebSocket runner, voice cloning, and video assembly. Full-stack setup scripts for missing models/nodes.

**Tech Stack:** Python 3.11, requests, websocket-client, moviepy, Ollama, ComfyUI, XTTS v2 (Coqui/TTS), PowerShell setup scripts

---

### Task 1: Project skeleton + config

**Files:**
- Create: `requirements.txt`
- Create: `config.py`
- Create: `topics.txt`
- Create: `.gitignore`
- Create: `README.md`

**Step 1:** Create requirements, config with ComfyUI path `C:\ComfyUI`, Ollama defaults, node ID placeholders, topic defaults.

**Step 2:** Create sample `topics.txt` with mode/ratio/lang examples.

**Step 3:** Commit.

---

### Task 2: ComfyUI utils (queue + websocket)

**Files:**
- Create: `utils.py`
- Create: `tests/test_utils_parse.py`

**Step 1:** Implement `queue_prompt`, `track_execution`, `get_history`, `find_output_files`.

**Step 2:** Unit-test JSON helpers / topic parser separately if split.

**Step 3:** Commit.

---

### Task 3: Topic parser + Director (Ollama)

**Files:**
- Create: `director.py`
- Create: `tests/test_topic_parser.py`

**Step 1:** Parse topic lines with optional `mode:`, `ratio:`, `lang:` prefixes.

**Step 2:** Ollama generate with strict JSON schema for scenes.

**Step 3:** Tests for parser; mock optional for Ollama.

**Step 4:** Commit.

---

### Task 4: ComfyUI runner

**Files:**
- Create: `comfy_runner.py`
- Create: `workflows/workflow_api.example.json`
- Create: `workflows/README.md`

**Step 1:** Load workflow JSON, inject prompt/seed/filename via config node map.

**Step 2:** Character mode: set IP-Adapter image input when configured.

**Step 3:** Example workflow stub documenting expected node roles.

**Step 4:** Commit.

---

### Task 5: Voice (XTTS) + Editor (MoviePy)

**Files:**
- Create: `voice.py`
- Create: `editor.py`
- Create: `assets/voices/README.md`

**Step 1:** XTTS synthesize from narration + speaker wav; fallback to pyttsx3/edge-tts if XTTS missing so pipeline still runs.

**Step 2:** MoviePy concat, attach audio, optional music ducking, simple captions.

**Step 3:** Commit.

---

### Task 6: Main orchestrator

**Files:**
- Create: `main.py`
- Create: `pipeline.py`

**Step 1:** Wire director → per-scene comfy → voice → editor.

**Step 2:** Batch topics, error log, dry-run flag (`--dry-run` skips GPU).

**Step 3:** Commit.

---

### Task 7: Setup scripts

**Files:**
- Create: `scripts/setup_env.ps1`
- Create: `scripts/install_comfy_nodes.ps1`
- Create: `scripts/download_models.md`

**Step 1:** venv + pip install.

**Step 2:** Clone recommended ComfyUI custom nodes into `C:\ComfyUI\custom_nodes`.

**Step 3:** Model download checklist (Flux FP8, text encoders, IP-Adapter, upscaler).

**Step 4:** Commit.

---

### Task 8: Smoke verification

**Step 1:** `python -c` import all modules.

**Step 2:** `pytest tests/ -q`

**Step 3:** `python main.py --dry-run` with sample topics.

**Step 4:** Final commit.
