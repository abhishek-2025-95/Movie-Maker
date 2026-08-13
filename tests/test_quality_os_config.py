import config
from comfy_runner import apply_scene_to_workflow


def test_quality_first_defaults():
    assert getattr(config, "QUALITY_FIRST", False) is True
    assert int(config.WAN_QUALITY_STEPS) >= 14
    assert float(getattr(config, "WAN_QUALITY_CFG", 0)) >= 4.0
    assert int(config.FLUX_STEPS) >= 24
    assert getattr(config, "QUALITY_ALLOW_KEN_BURNS_FALLBACK", True) is False
    assert getattr(config, "QUALITY_ALLOW_FREEZE_PAD", True) is False


def test_apply_scene_sets_flux_steps_on_still_graph():
    workflow = {
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "old"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "oldneg"}},
        "5": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 20}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "x"}},
    }
    out = apply_scene_to_workflow(
        workflow,
        visual_prompt="test scene",
        filename_prefix="dx_test",
        seed=42,
        width=768,
        height=1344,
        node_map=config.NODE_MAP_FLUX,
    )
    assert out["5"]["inputs"]["steps"] == int(config.FLUX_STEPS)
    assert int(config.FLUX_STEPS) >= 24
