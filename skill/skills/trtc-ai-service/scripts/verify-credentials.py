#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Three-key credential-less validation script (Phase 3 Stage 5).

Design Goals
------------
**The "atomic tool" for AI-driven key configuration flow**:
1. The AI writes user-pasted keys into ``.env`` via ``write_to_file``
2. The AI calls ``python scripts/verify-credentials.py [--type tencent|trtc|llm]``
3. This script **only** reads from .env / environment variables; it does **not** accept any keys as CLI arguments
4. Outputs **structured JSON** to stdout; the AI parses it to determine ok / failure and responds per SKILL.md §5.5

Output format (always valid JSON)::

    Single: {"ok": true,  "type": "tencent", "error": "",     "message": "...", "latency_ms": 320}
    Single: {"ok": false, "type": "trtc",    "error": "E002", "message": "...", "latency_ms": 0}
    Batch:  {"ok": true,  "type": "all", "items": [ ... ]}

Exit code: ``0`` means all passed; non-zero means at least one failure (for shell scripting).

Usage
-----
    python3 scripts/verify-credentials.py                  # validate all three
    python3 scripts/verify-credentials.py --type tencent   # Tencent Cloud only
    python3 scripts/verify-credentials.py --type trtc      # TRTC only
    python3 scripts/verify-credentials.py --type llm       # LLM only
    python3 scripts/verify-credentials.py --no-deep        # TRTC skip deep OpenAPI validation

Security Constraints (Red Lines)
--------------------------------
- Never pass keys via CLI arguments (no --secret-id / --api-key parameters)
- Never echo credential plaintext to stdout / stderr
- ``.env`` permissions (600) are set by the caller at write time (this script does not re-process)
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

# Suppress warnings from third-party libraries (e.g., urllib3 / NotOpenSSLWarning) sent to stderr,
# keeping stdout pure JSON and stderr silent — no noise for AI parsing
warnings.filterwarnings("ignore")

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.lib import credential_validators as cv  # noqa: E402


def _print_json(data: dict) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False))
    sys.stdout.write("\n")
    sys.stdout.flush()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify-credentials",
        description="Credential-less validation of three keys (reads from .env only, outputs structured JSON)",
    )
    parser.add_argument(
        "--type",
        choices=["tencent", "trtc", "llm", "all"],
        default="all",
        help="Validate a single key; default is all",
    )
    parser.add_argument(
        "--no-deep",
        action="store_true",
        help="Skip deep OpenAPI validation for TRTC; only local UserSig self-consistency check",
    )
    parser.add_argument(
        "--env-file",
        default="",
        help="Optional: specify .env path (default: capabilities/conversation-core/.env)",
    )
    args = parser.parse_args(argv)

    cv.load_dotenv(Path(args.env_file) if args.env_file else None)

    if args.type == "tencent":
        result = cv.validate_tencent()
        _print_json(result.to_dict())
        return 0 if result.ok else 1

    if args.type == "trtc":
        result = cv.validate_trtc(deep=not args.no_deep)
        _print_json(result.to_dict())
        return 0 if result.ok else 1

    if args.type == "llm":
        result = cv.validate_llm()
        _print_json(result.to_dict())
        return 0 if result.ok else 1

    # all
    batch = cv.validate_all()
    _print_json(batch.to_dict())
    return 0 if batch.ok else 1


if __name__ == "__main__":
    sys.exit(main())
