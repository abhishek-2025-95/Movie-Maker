import json
import urllib.request
import urllib.parse

class DirectorPipeline:
    def __init__(self, server_address="127.0.0.1:8188"):
        self.server_address = server_address

    def queue_prompt(self, workflow):
        data = json.dumps({"prompt": workflow}).encode('utf-8')
        req = urllib.request.Request(f"http://{self.server_address}/prompt", data=data)
        try:
            response = urllib.request.urlopen(req)
            return json.loads(response.read())
        except Exception as e:
            raise RuntimeError(f"ComfyUI Error: {e.read().decode('utf-8') if hasattr(e, 'read') else e}")

    def run_production_loop(self, storyboard_scenes):
        print("🎬 STARTING DIRECTORX PRODUCTION LOOP 🎬")
        for idx, scene in enumerate(storyboard_scenes):
            print(f"👉 Rendering Scene {idx + 1}: {scene['title']}")
            # Load your workflow template here and inject scene['prompt'] into the text node
            # self.queue_prompt(workflow)
        print("✅ All scenes queued successfully!")

if __name__ == "__main__":
    pipeline = DirectorPipeline()
    sample_scenes = [{"title": "The Awakening", "prompt": "Cinematic comic panel, dark fantasy thriller..."}]
    pipeline.run_production_loop(sample_scenes)