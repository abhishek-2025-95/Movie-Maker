"""P1 preflight unit tests (no GPU / no large downloads required)."""
from pathlib import Path

from quality_os.preflight import PreflightResult, check_p1


def test_check_p1_returns_structured_result():
    r = check_p1(require_ipadapter=True, require_realesrgan=True)
    assert isinstance(r, PreflightResult)
    assert hasattr(r, "ok")
    assert hasattr(r, "missing")
    assert isinstance(r.missing, list)
    # On a fresh box without weights, ok should be False and missing non-empty
    if not r.ok:
        assert len(r.missing) >= 1


def test_ipadapter_workflow_json_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / "workflows" / "flux_t2i_ipadapter_gguf_api.json").exists()
    assert (root / "workflows" / "node_map_flux_ipadapter_gguf.json").exists()
