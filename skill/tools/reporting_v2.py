"""Module entrypoint and re-export for TRTC reporting v2."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skills.trtc.tools.reporting_v2 import *  # noqa: F401,F403
from skills.trtc.tools.reporting_v2 import main

if __name__ == "__main__":
    sys.exit(main())
