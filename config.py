"""DirectorX local cinematic video factory configuration."""
from __future__ import annotations

from pathlib import Path

# --- Paths ---
ROOT = Path(__file__).resolve().parent
COMFYUI_ROOT = Path(r"C:\ComfyUI")
COMFYUI_OUTPUT = COMFYUI_ROOT / "output"
COMFYUI_INPUT = COMFYUI_ROOT / "input"
WORKFLOW_API = ROOT / "workflow_api.json"
WORKFLOW_EXAMPLE = ROOT / "workflows" / "workflow_api.example.json"
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

# --- ComfyUI node ID map ---
# Update these after exporting your real workflow_api.json from ComfyUI Dev Mode.
# Keys are logical roles; values are string node IDs in the API JSON.
NODE_MAP = {
    "positive_prompt": "6",       # CLIPTextEncode (Flux positive)
    "negative_prompt": "7",       # CLIPTextEncode negative (if present)
    "ksampler_seed": "3",         # KSampler / RandomNoise seed
    "save_prefix": "12",          # SaveVideo / VHS_VideoCombine filename_prefix
    "ipadapter_image": None,      # LoadImage node id for character ref (set when ready)
    "width": None,                # EmptyLatent / size node width input (optional)
    "height": None,               # EmptyLatent / size node height input (optional)
}

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
