"""Reporting v2 shim — delegates to ``skills/trtc/tools/reporting_v2.py``."""

from __future__ import annotations

from ._delegate import run_trtc_tool_main

if __name__ == "__main__":
    raise SystemExit(run_trtc_tool_main("reporting_v2"))
