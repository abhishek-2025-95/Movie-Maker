import os
import shutil

targets = {
    'wan2.2_i2v_low_noise_14B_Q4_K_M.gguf': 'C:/Users/user/Documents/ComfyUI/models/unet',
    'wan2.2_i2v_high_noise_14B_Q4_K_M.gguf': 'C:/Users/user/Documents/ComfyUI/models/unet',
    'umt5-xxl-enc-fp8_e4m3fn.safetensors': 'C:/Users/user/Documents/ComfyUI/models/clip',
    'wan_2.1_vae.safetensors': 'C:/Users/user/Documents/ComfyUI/models/vae'
}

print('🔍 Searching entire C: drive for model files...')
count = 0
for root, dirs, files in os.walk('C:/'):
    if any(skip in root.lower() for skip in ['windows', 'system32', '$recycle.bin', 'appdata/local/microsoft', 'program files', 'programdata']):
        continue
    for file_name in files:
        if file_name in targets:
            dest = targets[file_name]
            os.makedirs(dest, exist_ok=True)
            src = os.path.join(root, file_name)
            dst_file = os.path.join(dest, file_name)
            if not os.path.exists(dst_file):
                try:
                    shutil.copy2(src, dst_file)
                    print(f'✅ Found & Copied: {file_name}')
                    count += 1
                except Exception:
                    pass
            else:
                count += 1

print(f'✨ Finished! Total files ready: {count}/4')