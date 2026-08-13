with open('thriller_test.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('umt5-xxl-enc-fp8_e4m3fn.safetensors', 'umt5-xxl-enc-fp8_e4m3fn.safetensors')

with open('thriller_test.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ File name updated successfully in thriller_test.py!")