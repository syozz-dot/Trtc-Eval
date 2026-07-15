#!/usr/bin/env python3
"""PostToolUse hook — eval-only tool_call trace emitter.

Registered by phase3/eval_runner.py into the working-dir .claude/settings.json
right before an eval run, removed right after. Never distributed to end users.

Reads a Claude Code hook envelope from stdin (JSON), extracts the relevant
tool_response fields, resolves the TRTC session id from
{cwd}/.trtc-session.yaml, and appends one `tool_call` event to
~/.cache/trtc-traces/{trtc_session_id}.jsonl via phase3/tracer.emit_trace.

Field selection strictly follows observability/trace-schema.md §2.6 (v2).
Privacy rules enforced: no raw file content, no oldString/newString, no bash
stdout/stderr text — only byte counts and structural fields.

Always exits 0 (fail-open) so tracing failures never break the parent CLI.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add phase3/ to path so we can import tracer.py regardless of cwd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from tracer import emit_trace  # noqa: E402


def _resolve_trtc_session_id(cwd: str | None) -> tuple[str, str]:
    """Return (session_id, source) where source is 'trtc' or 'fallback'.

    Look for .trtc-session.yaml starting at cwd. If it exists and has a
    session_id field, that's the trusted TRTC session. Otherwise fall back to
    the harness's Claude conversation session id (consumer must filter on
    session_id_source).
    """
    candidates: list[Path] = []
    if cwd:
        candidates.append(Path(cwd) / ".trtc-session.yaml")
    # As a last resort, walk up from CLAUDE_PROJECT_DIR if set
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        candidates.append(Path(proj) / ".trtc-session.yaml")

    for p in candidates:
        if not p.exists():
            continue
        try:
            # Minimal yaml read: session_id is always a flat top-level key so
            # regex-lite line scanning avoids pulling in pyyaml.
            for line in p.read_text().splitlines():
                line = line.strip()
                if line.startswith("session_id:"):
                    val = line.split(":", 1)[1].strip().strip("'\"")
                    if val:
                        return val, "trtc"
        except Exception:
            continue

    return "", "fallback"


def _bash_is_error(tool_response: dict) -> bool:
    """Bash: interrupted flag only. exit_code is always null in envelope."""
    return bool(tool_response.get("interrupted"))


def _read_is_error(tool_response: dict | None) -> bool:
    if not isinstance(tool_response, dict):
        return True
    return "file" not in tool_response


def _write_is_error(tool_response: dict | None) -> bool:
    if not isinstance(tool_response, dict):
        return True
    return tool_response.get("type") not in ("create", "edit")


def _edit_is_error(tool_response: dict | None) -> bool:
    if not isinstance(tool_response, dict):
        return True
    return "filePath" not in tool_response


def _generic_is_error(tool_response) -> bool:
    if tool_response is None:
        return True
    if isinstance(tool_response, dict) and "error" in tool_response:
        return True
    return False


def _extract_fields(tool_name: str, envelope: dict) -> dict:
    """Pull the schema §2.6 fields out of the harness envelope.

    All optional fields default to None (schema-compliant nullable).
    Privacy: never touch content/oldString/newString/stdout/stderr text.
    """
    ti = envelope.get("tool_input") or {}
    tr = envelope.get("tool_response") or {}

    fields: dict = {
        "tool_name": tool_name,
        "duration_ms": envelope.get("duration_ms"),
        "tool_use_id": envelope.get("tool_use_id"),
        "is_error": False,
        "file_path": None,
        "num_lines": None,
        "total_lines": None,
        "write_type": None,
        "patch_ops": None,
        "stdout_bytes": None,
        "stderr_bytes": None,
        "interrupted": None,
    }

    if tool_name == "Read":
        fields["file_path"] = ti.get("file_path")
        file_obj = tr.get("file") if isinstance(tr, dict) else None
        if isinstance(file_obj, dict):
            fields["num_lines"] = file_obj.get("numLines")
            fields["total_lines"] = file_obj.get("totalLines")
        fields["is_error"] = _read_is_error(tr)

    elif tool_name == "Write":
        fields["file_path"] = ti.get("file_path")
        if isinstance(tr, dict):
            fields["write_type"] = tr.get("type")
            sp = tr.get("structuredPatch")
            if isinstance(sp, list):
                fields["patch_ops"] = len(sp)
        fields["is_error"] = _write_is_error(tr)

    elif tool_name == "Edit":
        fields["file_path"] = ti.get("file_path")
        if isinstance(tr, dict):
            sp = tr.get("structuredPatch")
            if isinstance(sp, list):
                fields["patch_ops"] = len(sp)
        fields["is_error"] = _edit_is_error(tr)

    elif tool_name == "Bash":
        if isinstance(tr, dict):
            stdout = tr.get("stdout")
            stderr = tr.get("stderr")
            if isinstance(stdout, str):
                fields["stdout_bytes"] = len(stdout)
            if isinstance(stderr, str):
                fields["stderr_bytes"] = len(stderr)
            fields["interrupted"] = tr.get("interrupted")
        fields["is_error"] = _bash_is_error(tr if isinstance(tr, dict) else {})

    else:
        fields["is_error"] = _generic_is_error(tr)

    return fields


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        envelope = json.loads(raw)
    except Exception:
        return 0  # fail-open

    tool_name = envelope.get("tool_name") or ""
    if not tool_name:
        return 0

    cwd = envelope.get("cwd")
    sid, source = _resolve_trtc_session_id(cwd)
    if not sid:
        # Harness will supply a Claude session_id; use it as fallback so the
        # event is not lost. Consumers filter on session_id_source.
        sid = envelope.get("session_id") or "unknown"

    payload = {
        "event": "tool_call",
        "session_id": sid,
        "session_id_source": source,
    }
    payload.update(_extract_fields(tool_name, envelope))
    emit_trace(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
