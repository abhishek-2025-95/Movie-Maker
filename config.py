"""DirectorX local cinematic video factory configuration."""
from __future__ import annotations

from pathlib import Path

# --- Paths ---
ROOT = Path(__file__).resolve().parent
COMFYUI_ROOT = Path(r"C:\ComfyUI")
COMFYUI_OUTPUT = COMFYUI_ROOT / "output"
COMFYUI_INPUT = COMFYUI_ROOT / "input"
WORKFLOW_API = ROOT / "workflow_api.json"  # default Wan I2V motion graph
WORKFLOW_FLUX = ROOT / "workflows" / "flux_t2i_api.json"
WORKFLOW_WAN = ROOT / "workflows" / "wan_i2v_api.json"
WORKFLOW_EXAMPLE = ROOT / "workflows" / "workflow_api.example.json"
# Two-stage: Flux still → Wan I2V (best quality). Set False to use only WORKFLOW_API.
TWO_STAGE = True
TOPICS_FILE = ROOT / "topics.txt"
TEMP_DIR = ROOT / "temp"
OUTPUT_DIR = ROOT / "final_outputs"
VOICE_SAMPLE = ROOT / "assets" / "voices" / "default.wav"
BGM_DIR = ROOT / "assets" / "music"
ERROR_LOG = TEMP_DIR / "errors.log"

# --- Servers ---
COMFYUI_HOST = "127.0.0.1:8188"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "llama3.1:8b"  # deepseek-r1:8b also available

# --- Video defaults ---
DEFAULT_MODE = "faceless"  # faceless | character
DEFAULT_RATIO = "9:16"  # 9:16 | 16:9
DEFAULT_LANG = "en"  # en | hi
SCENES_PER_VIDEO = 6
SECONDS_PER_SCENE = 5
FPS = 24

RATIO_SIZES = {
    "9:16": (768, 1344),
    "16:9": (1344, 768),
}

# Cinematic modifiers appended to every Flux prompt
CINEMATIC_SUFFIX = (
    "cinematic lighting, photorealistic, 35mm film still, shallow depth of field, "
    "high detail, no text, no watermark, no logo, no subtitles"
)

# --- ComfyUI node ID maps (from scripts/build_workflow_api.py) ---
# Re-run that script after editing graphs, or export from ComfyUI Dev Mode and remap.
NODE_MAP_FLUX = {
    "positive_prompt": "2",
    "negative_prompt": "3",
    "ksampler_seed": "5",
    "save_prefix": "7",
    "ipadapter_image": None,
    "width": "4",
    "height": "4",
}

NODE_MAP_WAN = {
    "positive_prompt": "19",
    "negative_prompt": "20",
    "ksampler_seed": "22",  # high-noise sampler; low-noise seed synced in comfy_runner
    "save_prefix": "26",
    "ipadapter_image": "10",  # LoadImage start frame
    "width": "21",
    "height": "21",
}

# Back-compat alias used when TWO_STAGE is False
NODE_MAP = NODE_MAP_WAN

NEGATIVE_PROMPT = (
    "blurry, low quality, deformed hands, extra fingers, watermark, text, logo, "
    "subtitles, cartoon, anime (unless requested), oversaturated"
)

# Voice
XTTS_LANGUAGE = {
    "en": "en",
    "hi": "hi",
}
VOICE_BACKEND = "auto"  # auto | xtts | edge

# Music ducking
BGM_VOLUME = 0.12
VOICE_VOLUME = 1.0
