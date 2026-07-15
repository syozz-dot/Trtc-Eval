#!/usr/bin/env python3
"""post-install-patch.py — safety-net patch script after capability assembly.

When to Call
------------
    SKILL.md §6 Path A Step 2.5 (after add-capability, before UI overlay)

What It Does
------------
1. **Fix legacy extension point misplacement**
   Early versions of `conversation-core/manifest.yaml` wrote `agent.before_push_text`
   as `before:push_text`, which add-capability.py interpreted as "insert at same indent
   before the `def push_text` line," resulting in class-scope placement that referenced
   local variables `session_id`/`text`, causing NameError.
   The new version uses sentinel anchor `_ext_before_push_text_` (inside push_text method body).
   This patch scans the deployed agent.py and moves any "class-scope misplaced injection block"
   into the correct method-body position. If already in the method body, it is skipped (idempotent).
   The same logic also covers `_ext_after_start_`.

2. **Auto-append .env default capability variables**
   recipe.yaml ui_overlay / capability adapter defaults (KB_ADAPTER=mock /
   HH_ADAPTER=local_queue, etc.) previously required manual .env editing. This patch
   appends missing entries to an existing .env without overwriting existing values.

3. **server.py StaticFiles html=True verification**
   Ensures `/static/admin/`, `/static/dev/`, etc. subdirectory access can fallback to index.html.

Output
------
    A JSON line (structured). Exit code 0 = all OK or idempotent skips; non-0 = anomalies
    requiring manual intervention.

Only modifies these whitelisted files:
    capabilities/conversation-core/src/agent.py
    capabilities/conversation-core/src/server.py
    capabilities/conversation-core/.env
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_PY = ROOT / "capabilities" / "conversation-core" / "src" / "agent.py"
SERVER_PY = ROOT / "capabilities" / "conversation-core" / "src" / "server.py"
ENV_FILE = ROOT / "capabilities" / "conversation-core" / ".env"

# .env 默认值（与 scenarios/customer-service/recipe.yaml 对齐）
ENV_DEFAULTS = {
    "KB_ADAPTER": "mock",
    "KB_TOP_K": "3",
    "KB_MIN_SCORE": "0.05",
    "HH_ADAPTER": "local_queue",
}

# Known capability injection block markers (by capability name)
CAP_MARKERS = ("human-handoff", "tool-calling", "session-summary", "knowledge-base")


# --------------------------------------------------------------------------- #
# 1. agent.py misplaced injection fix
# --------------------------------------------------------------------------- #
def _patch_agent_py(report: dict) -> None:
    if not AGENT_PY.exists():
        report["agent_py"] = {"ok": False, "skipped": True, "reason": "agent.py not found"}
        return

    src = AGENT_PY.read_text(encoding="utf-8")

    # Check whether each capability's marker still appears at 4-space indent in class scope
    # (correct position is 8+ spaces = inside method body)
    misplaced: list[str] = []
    for cap in CAP_MARKERS:
        marker = f"# [{cap}]"
        # Class scope 4 spaces + marker
        if re.search(rf"^    {re.escape(marker)}", src, re.MULTILINE):
            misplaced.append(cap)

    if not misplaced:
        report["agent_py"] = {"ok": True, "patched": [], "note": "no misplaced capability injections"}
        return

    # For each misplaced capability, strip it from class scope → move before the corresponding method body sentinel
    new_src = src
    moved: list[str] = []
    failures: list[dict] = []
    for cap in misplaced:
        marker = f"# [{cap}]"
        # Extract consecutive 4-space-indented block starting with the marker
        block_re = re.compile(
            rf"(?:^    {re.escape(marker)}[^\n]*\n(?:^    [^\n]*\n)+)",
            re.MULTILINE,
        )
        m = block_re.search(new_src)
        if not m:
            failures.append({"capability": cap, "reason": "marker found but block extract failed"})
            continue
        block_text = m.group(0)
        # Promote 4-space indent to 8-space (method body)
        rebased = "\n".join(
            ("    " + line) if line.startswith("    ") else line
            for line in block_text.splitlines()
        ) + "\n"
        # Choose sentinel: human-handoff before_push_text uses _ext_before_push_text_;
        # the same capability's after_start uses _ext_after_start_.
        # Simple heuristic: pick whichever sentinel appears first; decide by whether the cap references `text`.
        sentinel = (
            "_ext_before_push_text_"
            if "maybe_handoff(session_id, text" in block_text
            or "maybe_dispatch(text" in block_text
            or "record_user_turn(session_id, text" in block_text
            else "_ext_after_start_"
        )
        # Insert rebased before the sentinel comment line
        sentinel_re = re.compile(
            rf"^([ \t]*)# {re.escape(sentinel)}\b[^\n]*$",
            re.MULTILINE,
        )
        s_match = sentinel_re.search(new_src)
        if not s_match:
            failures.append({"capability": cap, "reason": f"sentinel {sentinel} not found in agent.py"})
            continue
        # Build insertion text (indent aligned to sentinel, i.e. 8 spaces)
        # rebased is already 8-space indented
        # First remove old misplaced block from new_src
        without_old = new_src[: m.start()] + new_src[m.end():]
        # Re-locate sentinel line (position may have shifted)
        s_match2 = re.compile(
            rf"^([ \t]*)# {re.escape(sentinel)}\b[^\n]*$",
            re.MULTILINE,
        ).search(without_old)
        if not s_match2:
            failures.append({"capability": cap, "reason": f"sentinel {sentinel} lost after stripping old block"})
            continue
        new_src = (
            without_old[: s_match2.start()]
            + rebased
            + without_old[s_match2.start():]
        )
        moved.append(cap)

    if new_src != src:
        AGENT_PY.write_text(new_src, encoding="utf-8")

    report["agent_py"] = {
        "ok": not failures,
        "patched": moved,
        "failed": failures,
    }


# --------------------------------------------------------------------------- #
# 2. server.py StaticFiles html=True verification
# --------------------------------------------------------------------------- #
def _patch_server_py(report: dict) -> None:
    if not SERVER_PY.exists():
        report["server_py"] = {"ok": False, "skipped": True, "reason": "server.py not found"}
        return
    src = SERVER_PY.read_text(encoding="utf-8")
    if "StaticFiles(directory=str(_DEMO_DIR), html=False)" in src:
        new_src = src.replace(
            "StaticFiles(directory=str(_DEMO_DIR), html=False)",
            "StaticFiles(directory=str(_DEMO_DIR), html=True)",
        )
        SERVER_PY.write_text(new_src, encoding="utf-8")
        report["server_py"] = {"ok": True, "patched": ["StaticFiles html=True"]}
    elif "StaticFiles(directory=str(_DEMO_DIR), html=True)" in src:
        report["server_py"] = {"ok": True, "patched": [], "note": "already html=True"}
    else:
        report["server_py"] = {"ok": True, "patched": [], "note": "no matching StaticFiles mount"}


# --------------------------------------------------------------------------- #
# 3. Append .env defaults (do not overwrite existing)
# --------------------------------------------------------------------------- #
def _patch_env(report: dict) -> None:
    if not ENV_FILE.exists():
        report["env"] = {"ok": True, "skipped": True, "reason": ".env not present yet (run setup-credentials first)"}
        return
    text = ENV_FILE.read_text(encoding="utf-8")
    existing_keys = {
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if "=" in line and not line.strip().startswith("#")
    }
    appended = []
    additions = [
        f"{k}={v}" for k, v in ENV_DEFAULTS.items() if k not in existing_keys
    ]
    if additions:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n# Added by post-install-patch.py (capability adapter defaults)\n"
        text += "\n".join(additions) + "\n"
        ENV_FILE.write_text(text, encoding="utf-8")
        appended = [a.split("=", 1)[0] for a in additions]
    report["env"] = {"ok": True, "appended": appended}


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    report: dict = {}
    try:
        _patch_agent_py(report)
        _patch_server_py(report)
        _patch_env(report)
    except Exception as exc:  # noqa: BLE001
        report["fatal"] = repr(exc)
        print(json.dumps(report, ensure_ascii=False))
        return 2
    overall_ok = all(
        v.get("ok", False) or v.get("skipped", False) for v in report.values()
    )
    report["ok"] = overall_ok
    print(json.dumps(report, ensure_ascii=False))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
