from comfy_runner import apply_scene_to_workflow


def test_apply_scene_injects_prompt_and_seed():
    workflow = {
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "old"}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "oldneg"}},
        "3": {"class_type": "KSampler", "inputs": {"seed": 1}},
        "12": {"class_type": "SaveImage", "inputs": {"filename_prefix": "x"}},
    }
    out = apply_scene_to_workflow(
        workflow,
        visual_prompt="neon alley",
        motion_prompt="slow pan left",
        filename_prefix="dx_test",
        seed=42,
    )
    assert "neon alley" in out["6"]["inputs"]["text"]
    assert "slow pan left" in out["6"]["inputs"]["text"]
    assert out["3"]["inputs"]["seed"] == 42
    assert out["12"]["inputs"]["filename_prefix"] == "dx_test"
    # original untouched
    assert workflow["6"]["inputs"]["text"] == "old"
