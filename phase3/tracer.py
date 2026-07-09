"""Trace logger shim (eval-side).

Mirrors the emit_trace() contract in agent-skills session.py so that Trtc-Eval's
PostToolUse hook writes to the same JSONL file the skill already writes to:

    ~/.cache/trtc-traces/{trtc_session_id}.jsonl

Rationale for duplicating instead of importing from skill code:
  - Trtc-Eval must run without any dependency on the skill package layout.
  - The skill's emit_trace is inline in session.py, not exposed as a lib.
  - Behaviour is trivial (append one JSON line), copying is cheaper than
    building a coupling.

Fail-open by design: a broken trace must never break the eval or the skill.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def trace_dir() -> Path:
    """Where trace files live. Same rule as skill: XDG_CACHE_HOME/trtc-traces
    (falls back to ~/.cache/trtc-traces)."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    d = Path(base) / "trtc-traces"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def emit_trace(event: dict) -> None:
    """Append one JSONL event. Always safe — errors are swallowed.

    `event` must contain at minimum {"event": str, "session_id": str}.
    A `ts` field is auto-injected if missing.
    """
    try:
        sid = event.get("session_id") or "unknown"
        path = trace_dir() / f"{sid}.jsonl"
        payload = {"ts": event.get("ts") or _iso_now(), **event}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # trace failure must never bubble; PostToolUse hooks run on every
        # tool invocation and killing one would degrade the parent CLI badly.
        pass
