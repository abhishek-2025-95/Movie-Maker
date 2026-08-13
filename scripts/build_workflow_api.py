"""Build DirectorX workflow_api.json + auto NODE_MAP from known ComfyUI node roles.

Creates two API graphs:
  - workflows/flux_t2i_api.json   (Flux FP8 still)
  - workflows/wan_i2v_api.json    (Wan 2.2 image-to-video)
  - workflow_api.json            (default = wan_i2v for motion stage)

Also prints / writes config NODE_MAP suggestions.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF_DIR = ROOT / "workflows"
OUT_DEFAULT = ROOT / "workflow_api.json"
CONFIG_PATH = ROOT / "config.py"


def flux_t2i_workflow() -> dict:
    """Flux.1-dev FP8 all-in-one stills (Comfy-Org checkpoint) + tiled VAE decode.

    Quality path only — never SD1.5 / Realistic Vision for live cinematic.
    Tiled VAE reduces gray-frame OOM spikes on 12GB.
    """
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "flux1-dev-fp8.safetensors"},
        },
        "9": {
            "class_type": "FluxGuidance",
            "inputs": {"guidance": 3.5, "conditioning": ["2", 0]},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "PLACEHOLDER_POSITIVE", "clip": ["1", 1]},
            "meta": {"title": "Positive Prompt"},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": (
                    "(mutated, extra limbs, multiple heads, deformed anatomy, conjoined bodies:1.5), "
                    "text, watermark, blurry, low quality, deformed hands, extra fingers, "
                    "cartoon, anime, cgi, 3d render"
                ),
                "clip": ["1", 1],
            },
            "meta": {"title": "Negative Prompt"},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 768, "height": 1344, "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 0,
                "steps": 22,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["9", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "6": {
            "class_type": "VAEDecodeTiled",
            "inputs": {
                "samples": ["5", 0],
                "vae": ["1", 2],
                "tile_size": 512,
                "overlap": 64,
                "temporal_size": 64,
                "temporal_overlap": 8,
            },
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "dx_still", "images": ["6", 0]},
        },
    }


def flux_t2i_gguf_workflow() -> dict:
    """Flux.1-dev GGUF stills for RTX 5070 12GB (UnetLoaderGGUF + DualCLIP + tiled VAE).

    Quant: Q5_K_S (city96 — Q5_K_M not published). T5/CLIP via DualCLIPLoader;
    VAEDecodeTiled tile_size=512 avoids end-of-job VAE OOM.
    """
    return {
        "1": {
            "class_type": "UnetLoaderGGUF",
            "inputs": {"unet_name": "flux1-dev-Q5_K_S.gguf"},
        },
        "8": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": "clip_l.safetensors",
                "clip_name2": "t5xxl_fp8_e4m3fn.safetensors",
                "type": "flux",
            },
        },
        "12": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "ae.safetensors"},
        },
        "9": {
            "class_type": "FluxGuidance",
            "inputs": {"guidance": 3.5, "conditioning": ["2", 0]},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "PLACEHOLDER_POSITIVE", "clip": ["8", 0]},
            "meta": {"title": "Positive Prompt"},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": (
                    "(mutated, extra limbs, multiple heads, deformed anatomy, conjoined bodies:1.5), "
                    "text, watermark, blurry, low quality, deformed hands, extra fingers, "
                    "cartoon, anime, cgi, 3d render"
                ),
                "clip": ["8", 0],
            },
            "meta": {"title": "Negative Prompt"},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 768, "height": 1344, "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 0,
                "steps": 22,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["9", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "6": {
            "class_type": "VAEDecodeTiled",
            "inputs": {
                "samples": ["5", 0],
                "vae": ["12", 0],
                "tile_size": 512,
                "overlap": 64,
                "temporal_size": 64,
                "temporal_overlap": 8,
            },
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "dx_still", "images": ["6", 0]},
        },
    }


def wan_i2v_workflow(*, gguf: bool = False) -> dict:
    """Wan 2.2 native I2V API graph with LoadImage start frame + SaveVideo.

    FP8 UNET pair (default) or GGUF Q4_K_M MoE pair (gguf=True) for 12GB VRAM.
    UMT5 text encoder forced to CPU so 9800X3D + system RAM own embeddings.
    """
    if gguf:
        high = {
            "class_type": "UnetLoaderGGUF",
            "inputs": {"unet_name": "wan2.2_i2v_high_noise_14B_Q4_K_M.gguf"},
        }
        low = {
            "class_type": "UnetLoaderGGUF",
            "inputs": {"unet_name": "wan2.2_i2v_low_noise_14B_Q4_K_M.gguf"},
        }
    else:
        high = {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
                "weight_dtype": "default",
            },
        }
        low = {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
                "weight_dtype": "default",
            },
        }
    return {
        "10": {
            "class_type": "LoadImage",
            "inputs": {"image": "example.png"},
            "meta": {"title": "Start Image / Character Ref"},
        },
        "11": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "wan",
                # 9800X3D + 32GB RAM: keep T5 off VRAM so 12GB GPU owns the UNET
                "device": "cpu",
            },
        },
        "12": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "wan_2.1_vae.safetensors"},
        },
        "13": high,
        "14": low,
        "17": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"model": ["13", 0], "shift": 5.0},
        },
        "18": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"model": ["14", 0], "shift": 5.0},
        },
        "19": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "PLACEHOLDER_POSITIVE", "clip": ["11", 0]},
            "meta": {"title": "Positive Prompt"},
        },
        "20": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": (
                    "blurry, static, low quality, watermark, text, logo, subtitles, "
                    "deformed hands, ugly"
                ),
                "clip": ["11", 0],
            },
            "meta": {"title": "Negative Prompt"},
        },
        "21": {
            "class_type": "WanImageToVideo",
            "inputs": {
                "positive": ["19", 0],
                "negative": ["20", 0],
                "vae": ["12", 0],
                "start_image": ["10", 0],
                "width": 480,
                "height": 832,
                "length": 81,
                "batch_size": 1,
            },
        },
        "22": {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": ["17", 0],
                "add_noise": "enable",
                "noise_seed": 0,
                "steps": 20,
                "cfg": 3.5,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["21", 0],
                "negative": ["21", 1],
                "latent_image": ["21", 2],
                "start_at_step": 0,
                "end_at_step": 10,
                "return_with_leftover_noise": "enable",
            },
        },
        "23": {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": ["18", 0],
                "add_noise": "disable",
                "noise_seed": 0,
                "steps": 20,
                "cfg": 3.5,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["21", 0],
                "negative": ["21", 1],
                "latent_image": ["22", 0],
                "start_at_step": 10,
                "end_at_step": 10000,
                "return_with_leftover_noise": "disable",
            },
        },
        "24": {
            "class_type": "VAEDecodeTiled",
            "inputs": {
                "samples": ["23", 0],
                "vae": ["12", 0],
                "tile_size": 512,
                "overlap": 64,
                "temporal_size": 64,
                "temporal_overlap": 8,
            },
        },
        "25": {
            "class_type": "CreateVideo",
            "inputs": {"images": ["24", 0], "fps": 16.0},
        },
        "26": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["25", 0],
                "filename_prefix": "dx_wan",
                "format": "auto",
                "codec": "auto",
            },
        },
    }


def detect_node_map(workflow: dict) -> dict[str, str | None]:
    positive = negative = seed = save = load_img = width = height = None

    for nid, node in workflow.items():
        if not isinstance(node, dict):
            continue
        ctype = node.get("class_type", "")
        title = (node.get("meta") or {}).get("title", "").lower()
        inputs = node.get("inputs") or {}

        if ctype == "CLIPTextEncode":
            if "negative" in title and negative is None:
                negative = nid
            elif positive is None:
                positive = nid
            elif negative is None and positive is not None:
                negative = nid

        if ctype in {"KSampler", "KSamplerAdvanced", "RandomNoise"}:
            if "seed" in inputs or "noise_seed" in inputs:
                seed = nid

        if ctype in {"SaveImage", "SaveVideo", "VHS_VideoCombine"}:
            save = nid

        if ctype == "LoadImage":
            load_img = nid

        if ctype in {"EmptySD3LatentImage", "EmptyLatentImage", "WanImageToVideo"}:
            if "width" in inputs:
                width = nid
            if "height" in inputs:
                height = nid

    # If two CLIP encodes and titles missing, first=pos second=neg by id order
    clip_ids = [
        nid
        for nid, n in workflow.items()
        if isinstance(n, dict) and n.get("class_type") == "CLIPTextEncode"
    ]
    if positive is None and clip_ids:
        positive = clip_ids[0]
    if negative is None and len(clip_ids) > 1:
        negative = clip_ids[1]

    return {
        "positive_prompt": positive,
        "negative_prompt": negative,
        "ksampler_seed": seed,
        "save_prefix": save,
        "ipadapter_image": load_img,
        "width": width,
        "height": height,
    }


def main() -> None:
    WF_DIR.mkdir(parents=True, exist_ok=True)
    flux = flux_t2i_workflow()
    flux_gguf = flux_t2i_gguf_workflow()
    wan = wan_i2v_workflow(gguf=False)
    wan_gguf = wan_i2v_workflow(gguf=True)

    flux_path = WF_DIR / "flux_t2i_api.json"
    flux_gguf_path = WF_DIR / "flux_t2i_gguf_api.json"
    wan_path = WF_DIR / "wan_i2v_api.json"
    wan_gguf_path = WF_DIR / "wan_i2v_gguf_api.json"
    flux_path.write_text(json.dumps(flux, indent=2), encoding="utf-8")
    flux_gguf_path.write_text(json.dumps(flux_gguf, indent=2), encoding="utf-8")
    wan_path.write_text(json.dumps(wan, indent=2), encoding="utf-8")
    wan_gguf_path.write_text(json.dumps(wan_gguf, indent=2), encoding="utf-8")

    # Default orchestrator workflow = Wan I2V (motion). Flux stills use flux path separately.
    OUT_DEFAULT.write_text(json.dumps(wan, indent=2), encoding="utf-8")

    flux_map = detect_node_map(flux)
    wan_map = detect_node_map(wan)

    print("Wrote", flux_path)
    print("Wrote", flux_gguf_path)
    print("Wrote", wan_path)
    print("Wrote", wan_gguf_path)
    print("Wrote", OUT_DEFAULT)
    print("\nSuggested NODE_MAP for Wan (default workflow_api.json):")
    print(json.dumps(wan_map, indent=2))
    print("\nSuggested NODE_MAP for Flux stills:")
    print(json.dumps(flux_map, indent=2))

    map_path = WF_DIR / "node_map_wan.json"
    map_path.write_text(json.dumps(wan_map, indent=2), encoding="utf-8")
    (WF_DIR / "node_map_flux.json").write_text(json.dumps(flux_map, indent=2), encoding="utf-8")
    (WF_DIR / "node_map_flux_gguf.json").write_text(
        json.dumps(detect_node_map(flux_gguf), indent=2), encoding="utf-8"
    )
    (WF_DIR / "node_map_wan_gguf.json").write_text(
        json.dumps(detect_node_map(wan_gguf), indent=2), encoding="utf-8"
    )
    print("\nSaved maps to workflows/node_map_*.json")


if __name__ == "__main__":
    main()
