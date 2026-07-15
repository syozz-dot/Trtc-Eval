"""Best-effort linkage with session-summary (optional capability).

When a handoff ticket is created, auto-generate a session summary and attach it to the ticket,
so agents can see customer issue context directly in the ticket details — no need to manually click "generate summary".

Design principles:
- Soft dependency: silently no-ops when session-summary is not installed; does not affect the handoff main flow.
- Non-blocking: defaults to heuristic summary (local, zero latency); does not call LLM in the ticket creation chain.
- Decoupled: dynamically loaded via conversation-core's _capability_loader;
  human-handoff has no static import dependency on session-summary.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_loader: Optional[Any] = None
_loader_resolved = False


def _get_loader() -> Optional[Any]:
    """Dynamically load conversation-core's _capability_loader (no relative imports, can load independently)."""
    global _loader, _loader_resolved
    if _loader_resolved:
        return _loader
    _loader_resolved = True
    try:
        # <root>/capabilities/human-handoff/src/summary_link.py → parents[3] = <root>
        repo_root = Path(__file__).resolve().parents[3]
        loader_path = (
            repo_root / "capabilities" / "conversation-core" / "src" / "_capability_loader.py"
        )
        if not loader_path.is_file():
            return None
        spec = importlib.util.spec_from_file_location("_hh_capability_loader", loader_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _loader = mod
    except Exception as exc:  # noqa: BLE001
        logger.info("session-summary link unavailable: %s", exc)
        _loader = None
    return _loader


def attach_summary_to_ticket(ticket: Any) -> None:
    """Generate an LLM narrative summary of the session chat and write it into the ticket's
    Description field (from AI connect → handoff trigger).

    The ticket Description becomes an LLM summary of the conversation, so agents see the
    context directly without a separate "Session Summary" block. session-summary not
    installed / any exception → silently skip (does not affect ticket creation main flow).
    """
    loader = _get_loader()
    if loader is None:
        return
    try:
        recorder_mod = loader.try_load_capability("session-summary", "src/recorder.py")
        summarizer_mod = loader.try_load_capability("session-summary", "src/summarizer.py")
        if recorder_mod is None or summarizer_mod is None:
            return
        session_id = ticket.user_id
        recorder = recorder_mod.get_recorder()
        rec = recorder.get(session_id)
        if rec is None:
            return  # No transcript recorded for this session (e.g. manually inserted test ticket), skip
        # LLM-generated one-paragraph summary of the chat → ticket Description.
        paragraph = summarizer_mod.summarize_paragraph(rec)
        if paragraph:
            ticket.description = paragraph
    except Exception as exc:  # noqa: BLE001
        logger.info("attach description summary skipped: %s", exc)
