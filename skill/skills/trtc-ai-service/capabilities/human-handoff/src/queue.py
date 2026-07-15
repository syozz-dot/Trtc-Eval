"""queue.py — compatibility facade.

Keeps the `attach_session` public symbol for manifest.extensions (agent.after_start)
to continue calling as `_hh_queue.attach_session(session_id, info=...)`.

Old version's `get_queue()` / `HandoffQueue` / `HandoffRecord` / `HandoffState`
are no longer used under the new architecture; kept as deprecated shims for gradual migration of third-party code.

New code should use directly:
- adapters.factory.get_client()    Get HandoffClient instance
- core.service.get_default_service() Get HandoffService instance
"""
from __future__ import annotations

import warnings
from typing import Any

from .adapters.factory import get_client
from .core.models import (  # noqa: F401  (backward compatible export)
    OverallStatus,
    Ticket,
    TicketStatus,
    TicketStatusEnum,
)


def attach_session(session_id: str, info: Any = None) -> None:
    """For conversation-core.after_start injection point use.

    Under the refactored implementation, "session registration" is done by client on create_ticket as needed;
    kept here as a no-op entry point to avoid breaking old calls from manifest.extensions.
    info parameter reserved for compatibility with old signature.
    """
    # Trigger client singleton init to surface config errors early during startup
    _ = get_client()
    return None


# --------------------------------------------------------------------
# Deprecated shim (for old tests / old external code gradual migration only; new code should not depend)
# --------------------------------------------------------------------
def get_queue():
    warnings.warn(
        "human_handoff.queue.get_queue() is deprecated; "
        "use adapters.factory.get_client() or core.service.get_default_service() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return get_client()


# Old symbol aliases (some integrators may directly import)
HandoffState = TicketStatusEnum
HandoffRecord = Ticket


__all__ = [
    "HandoffRecord",
    "HandoffState",
    "attach_session",
    "get_queue",
]
