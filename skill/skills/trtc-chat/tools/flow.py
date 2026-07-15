"""Flow CLI shim — delegates to ``skills/trtc/tools/flow.py``."""

from __future__ import annotations

from ._delegate import run_trtc_tool_main

if __name__ == "__main__":
    raise SystemExit(run_trtc_tool_main("flow"))
