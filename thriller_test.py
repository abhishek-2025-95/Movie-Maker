from director_core import DirectorPipeline

def run_smoke_test():
    print("🎬 PHASE 0: THRILLER SMOKE TEST (DIRECTORX CORE) 🎬")
    pipeline = DirectorPipeline()
    pipeline.patch_node("11", "CLIPLoader", {"clip_name": "umt5-xxl-enc-fp8_e4m3fn.safetensors", "type": "wan", "device": "default"})
    pipeline.execute_render()
    print("✅ Execution finished successfully!")

if __name__ == "__main__":
    run_smoke_test()
