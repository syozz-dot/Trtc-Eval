"""KB resolver shim — delegates to ``skills/trtc/tools/kb.py``."""

from __future__ import annotations

from ._delegate import run_trtc_tool_main

if __name__ == "__main__":
    raise SystemExit(run_trtc_tool_main("kb"))
