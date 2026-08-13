"""DirectorX local cinematic video factory configuration."""
from __future__ import annotations

from pathlib import Path

# --- Paths ---
ROOT = Path(__file__).resolve().parent
COMFYUI_ROOT = Path(r"C:\ComfyUI")
COMFYUI_OUTPUT = COMFYUI_ROOT / "output"
COMFYUI_INPUT = COMFYUI_ROOT / "input"
WORKFLOW_API = ROOT / "workflow_api.json"  # default Wan I2V motion graph
WORKFLOW_FLUX_FP8 = ROOT / "workflows" / "flux_t2i_api.json"
WORKFLOW_FLUX_GGUF = ROOT / "workflows" / "flux_t2i_gguf_api.json"
WORKFLOW_WAN_FP8 = ROOT / "workflows" / "wan_i2v_api.json"
WORKFLOW_WAN_GGUF = ROOT / "workflows" / "wan_i2v_gguf_api.json"
WORKFLOW_EXAMPLE = ROOT / "workflows" / "workflow_api.example.json"
# Two-stage: Flux still → Wan I2V (best quality). Set False to use only WORKFLOW_API.
TWO_STAGE = True

# RTX 5070 12GB + Ryzen 9800X3D profile: GGUF quants + --normalvram + T5 on CPU.
# Flux Q5_K_S (city96; Q5_K_M not published) + Wan MoE Q4_K_M (~9.65GB each).
USE_GGUF_5070_PROFILE = True
COMFY_LAUNCH_ARGS = ("--listen", "127.0.0.1", "--port", "8188", "--normalvram")
FLUX_GGUF_UNET = "flux1-dev-Q5_K_S.gguf"
WAN_GGUF_HIGH = "wan2.2_i2v_high_noise_14B_Q4_K_M.gguf"
WAN_GGUF_LOW = "wan2.2_i2v_low_noise_14B_Q4_K_M.gguf"
FLUX_AE_VAE = "ae.safetensors"
FLUX_CLIP_L = "clip_l.safetensors"
FLUX_T5 = "t5xxl_fp8_e4m3fn.safetensors"


def _model_exists(*relative: str, min_gb: float = 0.05) -> bool:
    for rel in relative:
        for base in (COMFYUI_ROOT / "models" / "unet", COMFYUI_ROOT / "models" / "text_encoders",
                     COMFYUI_ROOT / "models" / "clip", COMFYUI_ROOT / "models" / "vae",
                     COMFYUI_ROOT / "models" / "diffusion_models", COMFYUI_ROOT / "models" / "checkpoints"):
            p = base / rel
            if p.exists() and p.stat().st_size >= min_gb * (1024**3):
                return True
    return False


def gguf_flux_ready() -> bool:
    return (
        _model_exists(FLUX_GGUF_UNET, min_gb=7.0)
        and _model_exists(FLUX_CLIP_L, min_gb=0.2)
        and _model_exists(FLUX_T5, min_gb=4.0)
        and _model_exists(FLUX_AE_VAE, min_gb=0.2)
    )


def gguf_wan_ready() -> bool:
    return _model_exists(WAN_GGUF_HIGH, min_gb=8.0) and _model_exists(WAN_GGUF_LOW, min_gb=8.0)


def resolve_workflow_flux() -> Path:
    if USE_GGUF_5070_PROFILE and gguf_flux_ready() and WORKFLOW_FLUX_GGUF.exists():
        return WORKFLOW_FLUX_GGUF
    return WORKFLOW_FLUX_FP8


def resolve_workflow_wan() -> Path:
    if USE_GGUF_5070_PROFILE and gguf_wan_ready() and WORKFLOW_WAN_GGUF.exists():
        return WORKFLOW_WAN_GGUF
    return WORKFLOW_WAN_FP8


def still_backend() -> str:
    return "flux_gguf" if (USE_GGUF_5070_PROFILE and gguf_flux_ready()) else "flux_fp8"


def refresh_workflow_paths() -> None:
    """Re-bind WORKFLOW_* after GGUF downloads (call before pipeline / smokes)."""
    global WORKFLOW_FLUX, WORKFLOW_WAN, WORKFLOW_API, STILL_BACKEND, FLUX_CKPT, NODE_MAP_FLUX
    import json

    # Reset Flux node map to GGUF baseline, then upgrade if IP-Adapter P1 ready
    flux_map_gguf = ROOT / "workflows" / "node_map_flux_gguf.json"
    if flux_map_gguf.exists():
        NODE_MAP_FLUX = json.loads(flux_map_gguf.read_text(encoding="utf-8"))
    try:
        from quality_os.preflight import ipadapter_workflow_ready, resolve_flux_workflow_quality

        WORKFLOW_FLUX = resolve_flux_workflow_quality()
        from quality_os.character_lora import lora_ready

        lora_map = ROOT / "workflows" / "node_map_flux_ipadapter_lora_gguf.json"
        ip_map = ROOT / "workflows" / "node_map_flux_ipadapter_gguf.json"
        if lora_ready() and lora_map.exists():
            NODE_MAP_FLUX = json.loads(lora_map.read_text(encoding="utf-8"))
        elif ipadapter_workflow_ready() and ip_map.exists():
            NODE_MAP_FLUX = json.loads(ip_map.read_text(encoding="utf-8"))
    except Exception:
        WORKFLOW_FLUX = resolve_workflow_flux()
    WORKFLOW_WAN = resolve_workflow_wan()
    WORKFLOW_API = WORKFLOW_WAN
    STILL_BACKEND = still_backend()
    FLUX_CKPT = FLUX_GGUF_UNET if STILL_BACKEND == "flux_gguf" else "flux1-dev-fp8.safetensors"


# Back-compat names — refresh_workflow_paths() runs at end of this module.
WORKFLOW_FLUX = WORKFLOW_FLUX_FP8
WORKFLOW_WAN = WORKFLOW_WAN_FP8
TOPICS_FILE = ROOT / "topics.txt"
TEMP_DIR = ROOT / "temp"
OUTPUT_DIR = ROOT / "final_outputs"
VOICE_SAMPLE = ROOT / "assets" / "voices" / "default.wav"
BGM_DIR = ROOT / "assets" / "music"
ERROR_LOG = TEMP_DIR / "errors.log"

# --- Servers ---
COMFYUI_HOST = "127.0.0.1:8188"
# Hires Wan (576×1024 @ length 81–96) on 12GB lowvram can exceed 30 min
COMFY_JOB_TIMEOUT_S = 5400.0  # hires Wan on 12GB lowvram can exceed 60m
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "llama3.1:8b"  # deepseek-r1:8b also available

# --- Video defaults ---
DEFAULT_MODE = "faceless"  # faceless | character
DEFAULT_RATIO = "9:16"  # 9:16 | 16:9
DEFAULT_LANG = "en"  # en | hi
DEFAULT_STYLE = "live"  # live | animated
SCENES_PER_VIDEO = 3  # autonomous 3-act short (Setup → Escalation → Climax)
SECONDS_PER_SCENE = 5
FPS = 24

# Style packs for positive / negative conditioning
STYLE_SUFFIX = {
    "live": (
        "photorealistic, cinematic, 8k, 35mm film still, shallow depth of field, "
        "high detail, clean frame, no text, no letters, no writing, no typography, "
        "no watermark, no logo, no signage, no subtitles, no captions"
    ),
    "animated": (
        "premium cinematic anime, Netflix-animation quality, Makoto Shinkai inspired, "
        "rich color grading, volumetric god rays, emotional storytelling frames, "
        "highly detailed character design, consistent face and outfit, "
        "clean frame, no text, no letters, no watermark, no logo, no subtitles"
    ),
}

# Hardcoded Flux negative (anatomy + text + eyeline / look-back guardrails)
FLUX_NEGATIVE_PROMPT = (
    "(mutated, extra limbs, multiple heads, deformed anatomy, conjoined bodies, "
    "text, watermark, font:1.5), "
    "(looking at camera, eye contact with viewer, posing, portrait shot, "
    "looking back, over shoulder, facing camera:1.5), "
    "(circular clock, analog clock, single digit, overexposed text bloom, "
    "blown-out glowing numbers:1.4), "
    "(silhouette, backlit, hidden face, dark shadows on face, underexposed:1.5)"
)
# Character / reunion face readability (inject on face-focused beats)
# Wingsuit / action flight — fantasy morph bans ONLY (body chase beats NEED third-person).
ACTION_FLIGHT_NEGATIVE = (
    "(butterfly wings, monarch butterfly, insect wings, bat wings, dragon wings, "
    "feathered wings, bird wings, angel wings, plumage, costume wings, cape wings, "
    "mechanical wings, glowing membrane wings, separate wing appendages, fairy wings:1.55), "
    "(person standing, walking on ground, portrait, face visible:1.4)"
)
# FPV beat only — chase-cam / back-of-helmet is banned here, not on drone follow beats.
ACTION_FPV_NEGATIVE = (
    "(third-person, full body from behind, seeing own back, follow cam, over-the-shoulder, "
    "helmet from behind, back of head, shoulders in frame, person flying ahead of camera, "
    "drone chase behind flyer:1.55)"
)
ACTION_WINGSUIT_POSITIVE = (
    "REAL modern skydiving wingsuit like Squirrel / Phoenix-Fly: matte nylon/cordura "
    "fabric webbed between BOTH arms and torso AND between both legs (leg wing), "
    "tight black body with small orange reflective panels only — flat technical fabric "
    "panels, no separate wings growing from the back, no insect membranes, no feathers"
)
ACTION_FPV_POSITIVE = (
    "empty GoPro chest-mount point-of-view looking straight forward, "
    "immersive first-person only, canyon fills the entire frame, no body in shot"
)
# FPV still race — Flux chase-cam bias; pick best of N seeds by plate heuristic.
# Keep ≤3 on 12GB — each Flux still is ~10–15m; WS hangs risk rises with long races.
# Multi-seed races + bible exhaust Windows pagefile before Wan on 12GB — keep at 1 for stable completes.
ACTION_FPV_STILL_CANDIDATES = 1
ACTION_FPV_SCORE_EARLY_STOP = 1.35  # accept plate early if clearly chest-cam
ACTION_SUIT_BIBLE_CANDIDATES = 1
ACTION_SUIT_STILL_CANDIDATES = 1
ACTION_SUIT_BIBLE_PROMPT = (
    "photoreal product photo of a modern skydiving wingsuit on an athlete, "
    "three-quarter back view, matte black nylon/cordura body, small orange reflective "
    "panels on arms and legs only, fabric webbed between arms and torso AND between legs, "
    "flat technical panels under tension, sealed black helmet, compact parachute container, "
    "studio softbox + canyon backdrop, Red Bull TV documentary still, "
    "FORBIDDEN butterfly monarch insect bat dragon feathered angel costume wings"
)
# Quality OS — max-quality defaults for RTX 5070 12GB
QUALITY_FIRST = True
# Wan quality on 12GB — higher steps, stay at 480 (512 optional try is off by default).
# 16–20 steps OOM-kills Comfy mid-Wan on 12GB @ length 80. Keep graph default (14).
WAN_QUALITY_STEPS = 14
WAN_QUALITY_CFG = 4.5
WAN_QUALITY_TRY_512 = False
QUALITY_ALLOW_KEN_BURNS_FALLBACK = False
QUALITY_ALLOW_FREEZE_PAD = False
# Action Wan: shorter latent = less pagefile thrash; MoviePy freeze-pads to beat.
ACTION_WAN_LENGTH_CAP = 65
EXPORT_UPSCALE_UNSHARP = True  # light unsharp after lanczos to 1080p
EXPORT_UPSCALE_HQ_CHAIN = True  # sleep317-class eq+unsharp+noise
EXPORT_USE_REALESRGAN = True  # P1: generative upscale when RealESRGAN_x2plus + spandrel present
# Hard reset ComfyUI process before Wan (12GB) — /free alone still OOM-kills mid-job.
# Romance / action passes also force restart from screenplay.raw.
RESTART_COMFY_BEFORE_WAN = True
COMFYUI_MAIN = Path(r"C:\ComfyUI\main.py")
COMFYUI_PYTHON = Path(r"C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe")
COMFY_RESTART_WAIT_SEC = 120.0

FACE_FILL_POSITIVE = (
    "(soft front fill light, readable facial expressions, studio lighting, "
    "glowing faces:1.3)"
)
FACE_SILHOUETTE_NEGATIVE = (
    "(silhouette, backlit, hidden face, dark shadows on face, underexposed:1.5)"
)
# Reel / raw clock prop lock (injected into visual prompts)
REEL_CLOCK_POSITIVE = (
    "(standard rectangular digital smartphone clock, HH:MM time format, "
    "clear glowing typography:1.3)"
)
REEL_CLOCK_NEGATIVE = (
    "(circular clock, analog clock, single digit, overexposed text bloom, "
    "blown-out glowing numbers:1.4)"
)
# Continuity across stitched Wan clips (anti hard-cut DNA loss)
REEL_CONTINUITY_POSITIVE = (
    "(locked off camera, static POV, nightstand remains in frame:1.2)"
)
REEL_CONTINUITY_NEGATIVE = (
    "(handheld, changing perspective, new location, camera jump, "
    "different room, phone held in hands:1.3)"
)
# Appended to every Flux/Wan visual_prompt before submit (fights Wan softness)
VISUAL_SHARPNESS_SUFFIX = (
    "(ultra-sharp focus, highly detailed, 8k resolution, crisp cinematic lighting:1.2)"
)
OLLAMA_MAX_RETRIES = 3
ANATOMY_NEGATIVE = FLUX_NEGATIVE_PROMPT

STYLE_NEGATIVE = {
    "live": FLUX_NEGATIVE_PROMPT,
    "animated": (
        f"{FLUX_NEGATIVE_PROMPT}, photorealistic skin pores, live action, "
        "inconsistent character, western cartoon, clipart"
    ),
}

# Back-compat defaults (live)
CINEMATIC_SUFFIX = STYLE_SUFFIX["live"]
NEGATIVE_PROMPT = FLUX_NEGATIVE_PROMPT

# Static duo bible — ONLY used when LLM trinity is missing AND topic is not solitary
CHARACTER_BIBLE_A = "South Asian woman in a tan trench coat over maroon top"
CHARACTER_BIBLE_B = (
    "South Asian man with a short beard in a dark green jacket over navy shirt"
)
CHARACTER_BIBLE = f"{CHARACTER_BIBLE_A}, {CHARACTER_BIBLE_B}"

# Act-2 escalation: ban romance-positive looks + second body in frame
ACT2_EMOTION_NEGATIVE = (
    "smiling, happy, eye contact, together, couple, two people, second person, "
    "duo, pair, holding hands"
)
ACT2_EMOTION_POSITIVE = (
    "looking away, solitary, sad expression, distance, standing alone, "
    "no smile, emotional tension, turned away, single subject only"
)
ACT2_ISOLATE_CHAR = "A"  # A or B — solitary Act-2 subject
# Act-3 thriller climax: keep tension, kill smiles
ACT3_EMOTION_NEGATIVE = "(smiling, happy, relaxed:1.5)"
# Kill sci-fi hallway drift on climax plates
ACT3_LOCATION_NEGATIVE = (
    "(modern fluorescent lights, LED wall strips, sci-fi light bars, neon tubes, "
    "hospital corridor, office hallway, contemporary architecture, "
    "recessed ceiling panels:1.4)"
)
# Keep mechanical props readable in wide shots (no featureless bloom orbs)
PROP_WIDE_VISIBILITY = (
    "prop clearly readable with visible brass gears mechanical seams and carved detail, "
    "no featureless glowing orb, no pure light bloom hiding the artifact:1.25"
)
# Sensory layering — injected into every Flux/Wan visual (9.5+ depth)
SENSORY_BIBLE = (
    "SENSORY_BIBLE: high-frequency details like weathered textures, microscopic dust particles, "
    "caustic light reflections, volumetric god-rays, and chromatic aberration:1.3"
)
# Cinematic post on final stitch (35mm grain + vignette + grade)
ENABLE_CINEMATIC_LAYERING = True
CINE_GRAIN_STRENGTH = 0.015
CINE_VIGNETTE_STRENGTH = 0.32
CINE_GAMMA = 0.9
CINE_CONTRAST = 1.1

NARRATION_MIN_WORDS = 15
NARRATION_MAX_WORDS = 20  # hard sync window for ~5s VO
CAPTION_FADEOUT_SEC = 0.5
END_BLACK_HOLD_SEC = 1.0  # deliberate black, no text


# Character / face lock: prompt identity (+ optional Flux IP-Adapter). Never reuse Scene-1
# still for later acts — that freezes the story on one plate (3-act visual failure).
REQUIRE_SCENE1_REF_LOCK = True
CHARACTER_MASTER_STILL_LOCK = False  # unique Flux still + Wan clip per scene
# InstantX / IP-Adapter face lock — OFF by default on 12GB; if enabled MUST flush VRAM before Wan
ENABLE_INSTANTX = False
INSTANTX_REQUIRES_VRAM_FLUSH = True
CAPTION_STROKE_WIDTH = 2  # thin outline — heavy stroke ate white fill
CAPTION_RELATIVE_Y = 0.82  # legacy; absolute bottom margin is preferred
CAPTION_BOTTOM_MARGIN = 72  # keep full caption block on-screen
CAPTION_MAX_LINES = 3  # hard cap — prevents bottom overflow truncate
CAPTION_MAX_WORDS_PER_LINE = 7
CAPTION_FONT = "Montserrat-Bold"
CAPTION_FONTSIZE = 48  # smaller so 15–20 words fit in 3 lines
CAPTION_TEXTWRAP_WIDTH = 25  # Reel/raw: never mid-sentence cut
CAPTION_BOX_W = 960
CAPTION_COLOR = "white"
CAPTION_STROKE = "black"
# Raw / Reel overlay: top of frame (MoviePy relative Y)
RAW_CAPTION_POSITION = "top"  # top | bottom
RAW_CAPTION_Y_REL = 0.15


RATIO_SIZES = {
    # Flux.1-dev FP8 cinematic stills (Option C) — min 768x1344 for 9:16
    "9:16": (768, 1344),
    "16:9": (1344, 768),
}

# Final deliverable canvas after assemble / upscale
OUTPUT_SIZES = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

# Wan I2V — 480 + Comfy process-restart is the reliable 12GB path; 576 still dies mid-Wan
WAN_SIZES = {
    "9:16": (480, 832),
    "16:9": (832, 480),
}
WAN_LENGTH = 81  # ~5.06s @ 16fps
WAN_FLUSH_SLEEP_SEC = 12.0  # shorter settle when process restart is used
FORCE_GC_BEFORE_WAN = True  # gc.collect() + Comfy /free before Wan
FLUX_STEPS = 24  # Flux.1-dev quality sweet spot (20–25)
STILL_BACKEND = "flux_fp8"  # updated at runtime via still_backend() / refresh_workflow_paths()
FLUX_CKPT = "flux1-dev-fp8.safetensors"
ALLOW_SD15_STILLS = False
# Warn if drive is too full for pagefile + GGUF intermediates (crash class seen on this box).
MIN_FREE_DISK_GB_GGUF = 40.0


# Caption / export — MoviePy TextClip only (PyCaps killed)
CAPTION_COLOR = "white"
CAPTION_STROKE = "black"
EXPORT_PRESET = "slow"
EXPORT_BITRATE = "15000k"
UPSCALE_ON_EXPORT = True  # lanczos → OUTPUT_SIZES after assemble
# Soft grade for full-song lyric music videos (less mush than default 35mm crush)
MUSIC_MV_GRAIN = 0.012
MUSIC_MV_VIGNETTE = 0.18
MUSIC_MV_GAMMA = 0.95
MUSIC_MV_CONTRAST = 1.05
MUSIC_MV_WAN_LENGTH_CAP = 65  # ~4s @16fps — longer chorus beats OOM on 12GB
ROMANCE_WAN_LENGTH_CAP = 65  # ~4s @16fps — premium path script also ladders 65→81
USE_PYCAPS = False  # permanently disabled — illegible Playwright CSS
ALLOW_ANIMATED = False  # never use anime style unless user explicitly enables this
OLLAMA_NUM_GPU = 0  # force Ollama CPU-only so Flux/Wan own the 12GB
VALID_TRANSITIONS = ("hard_cut", "fade_to_black", "crossfade", "smash_cut", "none")
TRANSITION_DURATION = 0.85  # seconds for fade/crossfade blends

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
    "ksampler_seed": "23",  # seeds synced across all KSamplers in comfy_runner
    "save_prefix": "26",
    "ipadapter_image": "10",  # LoadImage start frame
    "width": "21",
    "height": "21",
}

# Back-compat alias used when TWO_STAGE is False
NODE_MAP = NODE_MAP_WAN

# Voice
XTTS_LANGUAGE = {
    "en": "en",
    "hi": "hi",
}
VOICE_BACKEND = "auto"  # auto | xtts | edge

# Music ducking
BGM_VOLUME = 0.12
VOICE_VOLUME = 1.0
REEL_WAN_LENGTH = 96  # ~6.0s @ 16fps — 2 beats ≈ 12s
# Hard cap for hires Wan (1024×576 / 576×1024) on 12GB — MoviePy freeze-pads to beat length
REEL_WAN_HIRES_LENGTH_CAP = 65  # ~4.0s @16fps — freeze-pad to beat; safer on 12GB
REEL_SECONDS_PER_SCENE = 6.0
REEL_LOOP_END_SILENCE = 0.5  # absolute mute at tail for seamless loop scare
DEFAULT_RAW_TEXT_OVERLAY = "Check your phone. Time is running out."
FORCE_NO_CAPTIONS = False  # CLI --no-captions or reel meta burn_captions=False

# Prefer GGUF workflows when quants are on disk (safe to call repeatedly).
refresh_workflow_paths()
