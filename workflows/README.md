# ComfyUI workflows for DirectorX

## Pre-built API graphs (ready)

| File | Role |
|------|------|
| `flux_t2i_api.json` | Flux FP8 text → still image |
| `wan_i2v_api.json` | Wan 2.2 image → video (default `../workflow_api.json`) |
| `node_map_flux.json` / `node_map_wan.json` | Auto-detected node IDs |

Rebuild anytime:

```powershell
python scripts\build_workflow_api.py
```

`config.py` already maps:
- `NODE_MAP_FLUX`
- `NODE_MAP_WAN`
- `TWO_STAGE = True` → Flux still then Wan I2V per scene

## Manual GUI path (optional upgrade)

1. Open ComfyUI → load blueprint **Image to Video (Wan 2.2)** + a Flux T2I graph
2. Settings → enable **Dev Mode** → **Save (API Format)**
3. Replace `workflows/*.json` and re-run `python scripts\build_workflow_api.py` OR paste IDs into `config.py`

## Required models

See `scripts/download_flux.ps1` / `scripts/download_models.md`.
