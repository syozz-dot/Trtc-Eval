"""trigger.py — compatibility facade.

Keeps the `maybe_handoff` / `is_handoff_intent` public symbols for manifest.extensions
(agent.before_push_text) to continue calling as `_hh_trigger.maybe_handoff(session_id, text)`,
internally delegated to the refactored core.service.HandoffService.

New code should use core.service / core.intent_detector directly; do not depend on this facade.
"""
from __future__ import annotations

from typing import Optional

from .core.intent_detector import is_handoff_intent  # noqa: F401  (public API)
from .core.service import get_default_service


def maybe_handoff(session_id: str, text: str) -> Optional[str]:
    """For conversation-core.before_push_text injection point use.

    Signature fully consistent with original: returns None when not triggered; returns a string when text has been replaced with handoff script.
    """
    return get_default_service().maybe_handoff(session_id, text)


__all__ = ["is_handoff_intent", "maybe_handoff"]
