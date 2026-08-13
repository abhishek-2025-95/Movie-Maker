"""Print GGUF profile readiness."""
from __future__ import annotations

import config

config.refresh_workflow_paths()
print("FLUX", config.WORKFLOW_FLUX)
print("WAN", config.WORKFLOW_WAN)
print("BACKEND", config.still_backend())
print("gguf_flux", config.gguf_flux_ready())
print("gguf_wan", config.gguf_wan_ready())
print("launch", config.COMFY_LAUNCH_ARGS)
