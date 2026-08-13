python -c "code = '''import json
import urllib.request
import urllib.parse
import os
import time
from PIL import Image

class DirectorPipeline:
    def __init__(self, server_address=\"127.0.0.1:8188\", llm_url=\"http://localhost:11434/api/generate\", workflow_path=\"workflow_api.json\", output_dir=\"output_panels\"):
        self.server_address = server_address
        self.llm_url = llm_url
        self.workflow_path = workflow_path
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def load_workflow(self):
        if not os.path.exists(self.workflow_path):
            raise FileNotFoundError(f\"Workflow template not found at {self.workflow_path}\")
        with open(self.workflow_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def generate_storyboard_from_llm(self, core_theme):
        print(f\"🤖 Generating dynamic storyboard using local LLM for theme: '{core_theme}'...\")
        prompt = f\"\"\"Create a 2-panel comic/webtoon storyboard for a thriller story based on this theme: '{core_theme}'. 
        Return ONLY a valid JSON list of objects, where each object has 'title' and 'prompt' keys. No extra text.
        Example format:
        [
          {\"title\": \"Scene 1\", \"prompt\": \"Cinematic panel description...\"},
          {\"title\": \"Scene 2\", \"prompt\": \"Cinematic panel description...\"}
        ]\"\"\"
        
        data = json.dumps({\"model\": \"llama3\", \"prompt\": prompt, \"stream\": False}).encode('utf-8')
        req = urllib.request.Request(self.llm_url, data=data, headers={\"Content-Type\": \"application/json\"})
        
        try:
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                raw_response = result.get(\"response\", \"[]\")
                # Clean up json format if LLM added markdown block
                if \"```json\" in raw_response:
                    raw_response = raw_response.split(\"```json\")[1].split(\"```\")[0].strip()
                elif \"```\" in raw_response:
                    raw_response = raw_response.split(\"```\")[1].split(\"```\")[0].strip()
                return json.loads(raw_response)
        except Exception as e:
            print(f\"⚠️ Local LLM connection failed or returned invalid JSON ({e}). Falling back to default storyboard.\")
            return [
                {\"title\": \"Scene 1: The Secret\", \"prompt\": f\"Cinematic webtoon panel, dark thriller atmosphere, {core_theme}, high contrast, dramatic shadows\"},
                {\"title\": \"Scene 2: The Trap\", \"prompt\": f\"Action webtoon panel, tense moment, {core_theme}, gritty style, highly detailed\"}
            ]

    def queue_prompt(self, workflow):
        data = json.dumps({\"prompt\": workflow}).encode('utf-8')
        req = urllib.request.Request(f\"http://{self.server_address}/prompt\", data=data)
        try:
            response = urllib.request.urlopen(req)
            return json.loads(response.read())
        except Exception as e:
            error_msg = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
            raise RuntimeError(f\"ComfyUI Error: {error_msg}\")

    def wait_and_download_output(self, prompt_id, panel_index):
        print(f\"⏳ Waiting for ComfyUI to finish rendering Panel {panel_index}...\")
        history_url = f\"http://{self.server_address}/history/{prompt_id}\"
        
        while True:
            try:
                with urllib.request.urlopen(history_url) as response:
                    history = json.loads(response.read().decode('utf-8'))
                    if prompt_id in history:
                        outputs = history[prompt_id]['outputs']
                        # Find the saved image node output
                        for node_id, node_output in outputs.items():
                            if 'images' in node_output:
                                img_info = node_output['images'][0]
                                filename = img_info['filename']
                                subfolder = img_info.get('subfolder', '')
                                file_type = img_info.get('type', 'output')
                                
                                # Download image
                                query = urllib.parse.urlencode({'filename': filename, 'subfolder': subfolder, 'type': file_type})
                                img_url = f\"http://{self.server_address}/view?{query}\"
                                
                                save_path = os.path.join(self.output_dir, f\"panel_{panel_index}.png\")
                                urllib.request.urlretrieve(img_url, save_path)
                                print(f\"   📥 Downloaded and saved: {save_path}\")
                                return save_path
            except Exception:
                pass
            time.sleep(3)

    def stitch_panels(self, image_paths, output_filename=\"final_webtoon.png\"):
        print(\"🧵 Stitching panels into a vertical webtoon layout...\")
        images = [Image.open(p) for p in image_paths if os.path.exists(p)]
        if not images:
            print(\"❌ No images found to stitch!\")
            return
            
        widths, heights = zip(*(i.size for i in images))
        max_width = max(widths)
        total_height = sum(heights)

        combined_image = Image.new('RGB', (max_width, total_height))
        y_offset = 0
        for img in images:
            # Resize image to max_width if necessary to maintain clean vertical stack
            if img.width != max_width:
                img = img.resize((max_width, int(img.height * (max_width / img.width))))
            combined_image.paste(img, (0, y_offset))
            y_offset += img.height

        final_path = os.path.join(self.output_dir, output_filename)
        combined_image.save(final_path)
        print(f\"✨ Webtoon successfully created: {final_path}\")

    def run_production_pipeline(self, core_theme=\"A secret agent uncovers a digital conspiracy\"):
        print(\"🎬 STARTING DIRECTORX FULL AUTOMATION PIPELINE 🎬\")
        
        # Step 1: Generate storyboard from Local LLM
        scenes = self.generate_storyboard_from_llm(core_theme)
        base_workflow = self.load_workflow()
        downloaded_panels = []

        # Step 2: Loop through scenes, patch, queue, and download
        for idx, scene in enumerate(scenes):
            print(f\"\\n👉 Processing Panel {idx + 1}: {scene.get('title', 'Untitled')}\")
            workflow = json.loads(json.dumps(base_workflow)) # Deep copy
            
            # Patch Text Encoder Loader
            if \"11\" in workflow:
                workflow[\"11\"][\"inputs\"][\"type\"] = \"wan\"
                workflow[\"11\"][\"inputs\"][\"clip_name\"] = \"umt5-xxl-enc-fp8_e4m3fn.safetensors\"

            # Inject prompt into text node (Node '6')
            if \"6\" in workflow:
                workflow[\"6\"][\"inputs\"][\"text\"] = scene[\"prompt\"]
                print(f\"   Prompt Injected: {scene['prompt'][:60]}...\")

            # Queue and wait for completion
            res = self.queue_prompt(workflow)
            prompt_id = res.get('prompt_id')
            print(f\"   ✅ Queued! Prompt ID: {prompt_id}\")
            
            saved_path = self.wait_and_download_output(prompt_id, idx + 1)
            if saved_path:
                downloaded_panels.append(saved_path)

        # Step 3: Stitch panels together
        if downloaded_panels:
            self.stitch_panels(downloaded_panels)

if __name__ == \"__main__\":
    pipeline = DirectorPipeline()
    pipeline.run_production_pipeline(core_theme=\"A high-stakes cyber thriller in a neon-lit corporate tower\")
'''; open('director_core.py', 'w', encoding='utf-8').write(code); print('✅ director_core.py fully updated with LLM + Stitching pipeline!')"