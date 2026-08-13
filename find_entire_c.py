import os
import shutil

comfy_dir = r'C:/Users/user/Documents/ComfyUI'
clip_dir = os.path.join(comfy_dir, 'models', 'clip')
vae_dir = os.path.join(comfy_dir, 'models', 'vae')
ckpt_dir = os.path.join(comfy_dir, 'models', 'checkpoints')

os.makedirs(clip_dir, exist_ok=True)
os.makedirs(vae_dir, exist_ok=True)
os.makedirs(ckpt_dir, exist_ok=True)

files_to_find = {
    'umt5-xxl-enc-fp8_e4m3fn.safetensors': clip_dir,
    'wan_2.1_vae.safetensors': vae_dir,
    'v1-5-pruned-emaonly-fp16.safetensors': ckpt_dir
}

print('🔍 Scanning the entire C: drive for all required models...')

found_count = 0

for target_file, dest_folder in files_to_find.items():
    destination = os.path.join(dest_folder, target_file)
    if os.path.exists(destination):
        print(f'✔️ Already in place: {target_file}')
        found_count += 1
        continue

    found = False
    for root, dirs, files in os.walk('C:/', topdown=True):
        root_lower = root.lower()
        if any(p in root_lower for p in ['windows', '$recycle.bin', 'system volume information', 'appdata/local/microsoft']):
            continue
            
        if target_file in files:
            src_path = os.path.join(root, target_file)
            if src_path != destination:
                print(f'\n📦 Found {target_file} at: {src_path}')
                try:
                    shutil.copy2(src_path, destination)
                    print(f'✅ Copied successfully to {dest_folder}!')
                    found = True
                    found_count += 1
                    break
                except Exception as e:
                    print(f'❌ Copy error: {e}')
            else:
                found = True
                found_count += 1
                break
                
    if not found:
        print(f'❌ {target_file} not found anywhere on C: drive.')

print(f'\n✨ Scan finished! Total ready: {found_count}/3 files.')
