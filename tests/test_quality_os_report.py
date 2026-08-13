import json

import config
from pipeline_wan import (
    should_use_two_pass,
    wan_quality_cfg,
    wan_quality_steps,
    write_quality_run_report,
)


def test_write_quality_run_report_keys(tmp_path):
    out = write_quality_run_report(tmp_path)
    assert out == tmp_path / "quality_run_report.json"
    assert out.exists()

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["quality_first"] is bool(getattr(config, "QUALITY_FIRST", True))
    assert data["wan_path"] == ("two_pass_moe" if should_use_two_pass() else "single_pass")
    assert data["wan_steps"] == wan_quality_steps()
    assert data["wan_cfg"] == wan_quality_cfg()
    assert data["flux_steps"] == int(config.FLUX_STEPS)
    assert data["upscale"] == (
        "hq_chain" if getattr(config, "EXPORT_UPSCALE_HQ_CHAIN", False) else "lanczos"
    )
    assert data["freeze_pad"] is bool(getattr(config, "QUALITY_ALLOW_FREEZE_PAD", False))
    assert data["ken_burns_fallback"] is bool(
        getattr(config, "QUALITY_ALLOW_KEN_BURNS_FALLBACK", False)
    )
