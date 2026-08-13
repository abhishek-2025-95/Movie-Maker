import os
import shutil

comfy_dir = r'C:/Users/user/Documents/ComfyUI'
clip_dir = os.path.join(comfy_dir, 'models', 'clip')
vae_dir = os.path.join(comfy_dir, 'models', 'vae')

os.makedirs(clip_dir, exist_ok=True)
os.makedirs(vae_dir, exist_ok=True)

files_to_find = {
    'umt5-xxl-enc-fp8_e4m3fn.safetensors': clip_dir,
    'wan_2.1_vae.safetensors': vae_dir
}

print('🔍 Searching local ComfyUI folders for existing files...')

for target_file, dest_folder in files_to_find.items():
    destination = os.path.join(dest_folder, target_file)
    if os.path.exists(destination):
        print(f'✔️ Already in place: {target_file}')
        continue
    
    found = False
    for root, dirs, files in os.walk(comfy_dir):
        if target_file in files:
            src_path = os.path.join(root, target_file)
            if src_path != destination:
                print(f'📦 Found {target_file} at: {src_path}')
                shutil.copy2(src_path, destination)
                print(f'✅ Copied successfully to {dest_folder}!')
                found = True
                break
    
    if not found:
        print(f'❌ Could not find {target_file} locally in ComfyUI.')

print('✨ Local scan and copy process finished!')