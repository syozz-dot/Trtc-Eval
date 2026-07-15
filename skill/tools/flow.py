"""Module entrypoint and re-export for the shared TRTC flow tool."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skills.trtc.tools import flow as _impl
from skills.trtc.tools.flow import *  # noqa: F401,F403
from skills.trtc.tools.flow import main

_cli_enter = _impl._cli_enter


if __name__ == "__main__":
    sys.exit(main())
