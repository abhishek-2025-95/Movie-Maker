import os
import shutil
from huggingface_hub import hf_hub_download, get_token

comfy_dir = r'C:/Users/user/Documents/ComfyUI'
clip_dir = os.path.join(comfy_dir, 'models', 'clip')
vae_dir = os.path.join(comfy_dir, 'models', 'vae')

os.makedirs(clip_dir, exist_ok=True)
os.makedirs(vae_dir, exist_ok=True)

token = get_token()
print(f"🔑 Token Status: {'Loaded Successfully' if token else 'Not Found'}\n")

# 1. UMT5 Text Encoder from Kijai/WanVideo_comfy
umt5_path = os.path.join(clip_dir, "umt5-xxl-enc-fp8_e4m3fn.safetensors")
if os.path.exists(umt5_path):
    print("✔️ UMT5 Text Encoder already exists.")
else:
    print("📥 Downloading UMT5 Text Encoder from Kijai/WanVideo_comfy...")
    try:
        downloaded = hf_hub_download(
            repo_id="Kijai/WanVideo_comfy",
            filename="umt5-xxl-enc-fp8_e4m3fn.safetensors",
            token=token
        )
        if downloaded and os.path.exists(downloaded):
            shutil.copy2(downloaded, umt5_path)
            print("✅ UMT5 downloaded and placed successfully!\n")
    except Exception as e:
        print(f"❌ Failed to download UMT5: {e}\n")

# 2. Wan 2.1 VAE from Comfy-Org/Wan_2.1_ComfyUI_repackaged
vae_path = os.path.join(vae_dir, "wan_2.1_vae.safetensors")
if os.path.exists(vae_path):
    print("✔️ Wan 2.1 VAE already exists.")
else:
    print("📥 Downloading Wan 2.1 VAE from Comfy-Org/Wan_2.1_ComfyUI_repackaged...")
    try:
        downloaded = hf_hub_download(
            repo_id="Comfy-Org/Wan_2.1_ComfyUI_repackaged",
            subfolder="split_files/vae",
            filename="wan_2.1_vae.safetensors",
            token=token
        )
        if downloaded and os.path.exists(downloaded):
            shutil.copy2(downloaded, vae_path)
            print("✅ Wan 2.1 VAE downloaded and placed successfully!\n")
    except Exception as e:
        print(f"❌ Failed to download Wan 2.1 VAE: {e}\n")

print("✨ All download processes completed!")