import os
import shutil
from huggingface_hub import hf_hub_download

clip_dir = r'C:/Users/user/Documents/ComfyUI/models/clip'
vae_dir = r'C:/Users/user/Documents/ComfyUI/models/vae'

os.makedirs(clip_dir, exist_ok=True)
os.makedirs(vae_dir, exist_ok=True)

# 1. UMT5 Sources (Multiple Fallbacks)
umt5_sources = [
    {"repo_id": "Kijai/HunyuanVideo_repackaged", "filename": "text_encoders/umt5-xxl-enc-fp8_e4m3fn.safetensors"},
    {"repo_id": "Comfy-Org/HunyuanVideo_ComfyUI", "filename": "text_encoders/umt5-xxl-enc-fp8_e4m3fn.safetensors"},
    {"repo_id": "Comfy-Org/stable-diffusion-3-medium", "filename": "text_encoders/umt5-xxl-enc-fp8_e4m3fn.safetensors"},
    {"repo_id": "Comfy-Org/T5_XXL_fp8", "filename": "umt5_xxl_fp8_e4m3fn.safetensors"}
]

print('📥 Downloading UMT5 Text Encoder (Auto-trying sources)...')
umt5_success = False
for src in umt5_sources:
    try:
        print(f"-> Trying repo: {src['repo_id']}...")
        p1 = hf_hub_download(repo_id=src["repo_id"], filename=src["filename"])
        shutil.copy2(p1, os.path.join(clip_dir, 'umt5-xxl-enc-fp8_e4m3fn.safetensors'))
        print('✅ UMT5 downloaded successfully!')
        umt5_success = True
        break
    except Exception as e:
        print(f"   (Failed, trying next...)")

if not umt5_success:
    print('❌ All UMT5 sources failed.')

# 2. VAE Sources (Multiple Fallbacks)
vae_sources = [
    {"repo_id": "Kijai/WanVideoWrapper", "filename": "wan_2.1_vae.safetensors"},
    {"repo_id": "Comfy-Org/Wan2.1_ComfyUI_repackaged", "filename": "vae/wan_2.1_vae.safetensors"},
    {"repo_id": "Wan-AI/Wan2.1", "filename": "vae/wan_2.1_vae.safetensors"},
    {"repo_id": "Kijai/WanVideoWrapper_test", "filename": "wan_2.1_vae.safetensors"}
]

print('\n📥 Downloading Wan 2.1 VAE (Auto-trying sources)...')
vae_success = False
for src in vae_sources:
    try:
        print(f"-> Trying repo: {src['repo_id']}...")
        p2 = hf_hub_download(repo_id=src["repo_id"], filename=src["filename"])
        shutil.copy2(p2, os.path.join(vae_dir, 'wan_2.1_vae.safetensors'))
        print('✅ VAE downloaded successfully!')
        vae_success = True
        break
    except Exception as e:
        print(f"   (Failed, trying next...)")

if not vae_success:
    print('❌ All VAE sources failed.')

print('\n✨ All processes finished!')