import os, shutil
targets = {'wan2.2_i2v_low_noise_14B_Q4_K_M.gguf': r'C:\Users\user\Documents\ComfyUI\models\unet', 'wan2.2_i2v_high_noise_14B_Q4_K_M.gguf': r'C:\Users\user\Documents\ComfyUI\models\unet', 'umt5-xxl-enc-fp8_e4m3fn.safetensors': r'C:\Users\user\Documents\ComfyUI\models\clip', 'wan_2.1_vae.safetensors': r'C:\Users\user\Documents\ComfyUI\models\vae'}
for f, d in targets.items():
 os.makedirs(d, exist_ok=True)
 tp = os.path.join(d, f)
 if not os.path.exists(tp):
  for r in [r'C:\Users\user\Documents\DirectorX', r'C:\Users\user\Downloads', r'C:\Users\user\Documents\ComfyUI']:
   if os.path.exists(r):
    for dp, _, fns in os.walk(r):
     if f in fns:
      shutil.copy2(os.path.join(dp, f), tp)
      print(f'Successfully Placed: {f}')
      break
