import urllib.request
import json
import random
import time

try:
    with open('flux_t2i_gguf_api.json', 'r', encoding='utf-8') as f:
        workflow = json.load(f)
except FileNotFoundError:
    print("Error: flux_t2i_gguf_api.json nahi mila. Ensure you are running this from DirectorX folder.")
    exit()

prompt_node_id = None
prompt_key = None
seed_node_id = None
seed_key = None

# Universal search: Har node ke inputs mein 'text' key dhoondhna
for node_id, node in workflow.items():
    inputs = node.get('inputs', {})
    for k, v in inputs.items():
        if k == 'text' and isinstance(v, str) and len(v) > 3:
            prompt_node_id = node_id
            prompt_key = k
        if k in ['seed', 'noise_seed']:
            seed_node_id = node_id
            seed_key = k

print(f"Detected Prompt Node ID: {prompt_node_id} | Seed Node ID: {seed_node_id}")

# Agar tab bhi na mile, toh debug ke liye saare nodes print kar do
if not prompt_node_id:
    print("Error: 'text' key wala node nahi mila. Yeh raha aapke workflow ke available nodes ka debug info:")
    for nid, n in workflow.items():
        print(f"Node ID: {nid} | Class: {n.get('class_type')} | Inputs: {list(n.get('inputs', {}).keys())}")
    exit()

angles = [
    "looking directly at camera", 
    "looking slightly away", 
    "subtle smile", 
    "neutral expression", 
    "head tilted slightly"
]

print("Starting generation of 30 dataset images...")

for i in range(30):
    angle = random.choice(angles)
    new_prompt = f"Ultra-realistic macro portrait of a 23-year-old beautiful Indian woman, sharp facial features, almond-shaped eyes, subtle natural makeup, wearing a simple elegant pastel peach kurti, {angle}. Highly detailed natural skin texture, visible pores, peach fuzz, f/1.8 depth of field, 85mm lens. Soft studio lighting, dark solid gray background, 8k resolution, raw photo."
    
    workflow[prompt_node_id]['inputs'][prompt_key] = new_prompt
    if seed_node_id:
        workflow[seed_node_id]['inputs'][seed_key] = random.randint(100000, 999999999)
        
    data = json.dumps({"prompt": workflow}).encode('utf-8')
    req = urllib.request.Request("http://127.0.0.1:8188/prompt", data=data)
    
    try:
        urllib.request.urlopen(req)
        print(f"[{i+1}/30] Sent image request to ComfyUI (Angle: {angle})")
    except Exception as e:
        print(f"Error sending request for image {i+1}: {e}")
        
    time.sleep(0.5)

print("All 30 requests queued successfully! ComfyUI terminal mein check karein.")