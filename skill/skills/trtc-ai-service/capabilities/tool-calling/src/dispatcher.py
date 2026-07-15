"""Text injection interceptor: recognize "/tool" invocations from the conversation stream.

Expected text format:
    /tool <name> {json_params}

Example:
    /tool get_order {"order_id": "A1234"}

Dispatcher parses and calls ToolRegistry, returning the result as a structured string,
which is then forwarded to the LLM by conversation-core's injection point.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .registry import get_loader

_TOOL_RE = re.compile(r"^\s*/tool\s+([A-Za-z0-9_\-]{1,64})\s*(\{.*\})?\s*$", re.DOTALL)
_MAX_TEXT_LEN = 4096


def maybe_dispatch(text: str) -> Optional[str]:
    """Recognize "/tool" trigger, return new text with tool result; return None when not triggered."""
    if not text or len(text) > _MAX_TEXT_LEN:
        return None
    m = _TOOL_RE.match(text)
    if not m:
        return None
    name = m.group(1)
    raw_params = m.group(2) or "{}"
    try:
        params = json.loads(raw_params)
        if not isinstance(params, dict):
            params = {}
    except json.JSONDecodeError:
        params = {}
    result = get_loader().call(name, params)
    payload = {
        "tool": result.tool,
        "track": result.track,
        "ok": result.ok,
        "output": result.output,
        "error": result.error,
        "latency_ms": result.latency_ms,
        "fallback_chain": result.fallback_chain,
    }
    # Return in convention block, making it easy for LLM system prompt to recognize tool results
    return (
        f"[tool_result name={result.tool} track={result.track} ok={result.ok}]\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n[/tool_result]"
    )
