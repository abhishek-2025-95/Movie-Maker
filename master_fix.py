import os

old_name = "umt5-xxl-enc-fp8_e4m3fn.safetensors"
new_name = "umt5-xxl-enc-fp8_e4m3fn.safetensors"

found_and_fixed = False

for filename in os.listdir('.'):
    if filename.endswith('.py') or filename.endswith('.json'):
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if old_name in content:
            content = content.replace(old_name, new_name)
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Success: Updated file -> {filename}")
            found_and_fixed = True

if not found_and_fixed:
    print("⚠️ Purana naam kisi file mein nahi mila. Shayad pehle hi update ho chuka hai!")