import os
import shutil

clip_target = r'C:/Users/user/Documents/ComfyUI/models/clip'
vae_target = r'C:/Users/user/Documents/ComfyUI/models/vae'

missing = {
    'umt5-xxl-enc-fp8_e4m3fn.safetensors': clip_target,
    'wan_2.1_vae.safetensors': vae_target
}

print('🔍 Searching for missing CLIP and VAE files...')
for root, dirs, files in os.walk('C:/'):
    if any(skip in root.lower() for skip in ['windows', 'system32', '$recycle.bin', 'appdata/local/microsoft', 'program files', 'programdata']):
        continue
    for f in files:
        if f in missing:
            dest = missing[f]
            os.makedirs(dest, exist_ok=True)
            src = os.path.join(root, f)
            dst = os.path.join(dest, f)
            if not os.path.exists(dst):
                try:
                    shutil.copy2(src, dst)
                    print(f'✅ Copied {f} to {dest}')
                except Exception:
                    pass
            else:
                print(f'✔️ Already in place: {f}')
print('✨ Done!')
