"""In-process satisfaction feedback store (CSAT).

Lightweight memory store keyed by session_id. Used by HandoffService.submit_feedback
so the dashboard can look up a session's rating without requiring a ticket to exist.

Why memory-only?
- The default adapter (HH_ADAPTER=local_queue) is itself in-process, so an in-memory
  feedback store keeps the demo self-contained with zero external dependencies.
- Production deployments that persist tickets out-of-band should swap this for a
  persistent sink; the public surface (make_feedback / save_feedback / get_feedback)
  stays stable.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, Optional

_lock = threading.RLock()
_store: Dict[str, Dict[str, Any]] = {}


def make_feedback(rating: int, comment: str = "") -> Dict[str, Any]:
    """Build a normalized feedback record (does not persist)."""
    rating = int(rating)
    if rating < 1:
        rating = 1
    elif rating > 5:
        rating = 5
    return {
        "feedback_id": f"fb_{uuid.uuid4().hex[:12]}",
        "rating": rating,
        "comment": (comment or "").strip()[:1000],
        "created_at": time.time(),
    }


def save_feedback(session_id: str, feedback: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a feedback record keyed by session_id (overwrites prior entry)."""
    if not session_id:
        raise ValueError("session_id is required")
    with _lock:
        _store[session_id] = dict(feedback)
    return feedback


def get_feedback(session_id: str) -> Optional[Dict[str, Any]]:
    """Return the stored feedback for a session, or None if not rated yet."""
    if not session_id:
        return None
    with _lock:
        fb = _store.get(session_id)
        return dict(fb) if fb is not None else None
