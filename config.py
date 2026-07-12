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
SCENES_PER_VIDEO = 8  # ~40s Shorts-length storytelling
SECONDS_PER_SCENE = 5
FPS = 24

RATIO_SIZES = {
    # Generation sizes tuned for RTX 5070 12GB (editor still outputs target aspect)
    "9:16": (576, 1024),
    "16:9": (1024, 576),
}

# Wan I2V native sizes / frames (keep modest for VRAM)
WAN_SIZES = {
    "9:16": (480, 832),
    "16:9": (832, 480),
}
WAN_LENGTH = 81  # ~5s at 16fps × 8 scenes ≈ 40s final video
FLUX_STEPS = 12  # quality/speed balance on 5070

# Cinematic modifiers appended to every Flux / Wan positive prompt
CINEMATIC_SUFFIX = (
    "cinematic lighting, photorealistic, 35mm film still, shallow depth of field, "
    "high detail, clean frame, no text, no letters, no writing, no typography, "
    "no watermark, no logo, no signage, no subtitles, no captions"
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
    "ksampler_seed": "22",  # seeds synced across all KSamplers in comfy_runner
    "save_prefix": "26",
    "ipadapter_image": "10",  # LoadImage start frame
    "width": "21",
    "height": "21",
}

# Back-compat alias used when TWO_STAGE is False
NODE_MAP = NODE_MAP_WAN

# Hard negative conditioning — kill gibberish AI text / watermarks in-frame
NEGATIVE_PROMPT = (
    "text, typography, watermark, words, lettering, font, sign, logo, subtitle, "
    "caption, title card, writing, alphabet, characters, glyphs, numbers overlay, "
    "UI, HUD, poster text, newspaper headline, engraved letters, neon sign text, "
    "blurry, low quality, deformed hands, extra fingers, oversaturated, "
    "cartoon, anime (unless requested), static noise"
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
