"""human-handoff core models.

Defines unified domain models:
- TicketStatusEnum  Ticket status (aligned with business_contract.ticket.status_query.response.status)
- Ticket            Complete ticket record (transport object between adapters)
- TicketStatus      Lightweight status view (returned by status_query)
- OverallStatus     Overall queue status (dashboard use)

The core layer does not know any specific backend implementation; all adapters must use this module's data structures.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TicketStatusEnum(str, Enum):
    """Ticket status enum.

    Business semantics mapping:
    - PENDING    User has applied; not yet assigned an agent (equivalent to old HandoffState.WAITING)
    - PROCESSING Agent assigned, processing (equivalent to old HandoffState.CONNECTED)
    - CLOSED     Agent closed ticket
    - CANCELED   User actively canceled
    - TIMEOUT    Timeout, no agent connected
    """

    PENDING = "pending"
    PROCESSING = "processing"
    CLOSED = "closed"
    CANCELED = "canceled"
    TIMEOUT = "timeout"


# Status name mapping for old API compatibility (HandoffState era)
_LEGACY_STATE_MAP = {
    TicketStatusEnum.PENDING.value: "waiting",
    TicketStatusEnum.PROCESSING.value: "connected",
    TicketStatusEnum.CLOSED.value: "closed",
    TicketStatusEnum.CANCELED.value: "canceled",
    TicketStatusEnum.TIMEOUT.value: "timeout",
}


def to_legacy_state(status: str) -> str:
    """Convert new TicketStatusEnum value back to old API state name."""
    if not status:
        return "idle"
    return _LEGACY_STATE_MAP.get(status, status)


@dataclass
class Ticket:
    """Ticket record. Transport object between adapters.

    user_id and ticket_id default to the same value in LocalQueue implementation (using session_id),
    REST implementation uses ticket_id returned by the business side.
    """

    ticket_id: str
    user_id: str
    subject: str = ""
    description: str = ""
    priority: str = "normal"
    status: str = TicketStatusEnum.PENDING.value
    queue_position: int = 0
    eta_seconds: int = 0
    agent_id: Optional[str] = None
    transcript: List[str] = field(default_factory=list)
    reason: str = ""                          # Trigger reason summary (compatible with old field)
    created_at: Optional[float] = None
    updated_at: Optional[float] = None
    closed_at: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new_id() -> str:
        return f"tk_{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "session_id": self.user_id,
            "user_id": self.user_id,
            "subject": self.subject,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "queue_position": self.queue_position,
            "eta_seconds": self.eta_seconds,
            "agent_id": self.agent_id,
            "transcript": list(self.transcript),
            "reason": self.reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "closed_at": self.closed_at,
            # Written at ticket creation by human-handoff - session-summary linkage (None if capability not installed)
            "session_summary": self.extra.get("session_summary"),
            # Written by HandoffService.submit_feedback (None if not yet rated)
            "feedback": self.extra.get("feedback"),
        }

    def to_legacy_dict(self) -> dict:
        """Field format returned by old REST API (/api/v1/handoff/*), keeps Web Demo compatibility."""
        return {
            "session_id": self.user_id,
            "state": to_legacy_state(self.status),
            "reason": self.reason,
            "requested_at": self.created_at,
            "connected_at": self.updated_at if self.status == TicketStatusEnum.PROCESSING.value else None,
            "closed_at": self.closed_at,
            "agent_id": self.agent_id,
            "queue_position": self.queue_position,
            "estimated_wait_seconds": self.eta_seconds,
        }


@dataclass
class TicketStatus:
    """Response model corresponding to business_contract.ticket.status_query."""

    ticket_id: str
    status: str
    agent_id: Optional[str] = None
    queue_position: int = 0
    eta_seconds: int = 0
    updated_at: Optional[float] = None

    @classmethod
    def from_ticket(cls, t: Ticket) -> "TicketStatus":
        return cls(
            ticket_id=t.ticket_id,
            status=t.status,
            agent_id=t.agent_id,
            queue_position=t.queue_position,
            eta_seconds=t.eta_seconds,
            updated_at=t.updated_at or t.created_at,
        )


@dataclass
class OverallStatus:
    agent_pool_size: int
    available_agents: int
    waiting: int
    connected: int
    capacity: int

    def to_dict(self) -> dict:
        return {
            "agent_pool_size": self.agent_pool_size,
            "available_agents": self.available_agents,
            "waiting": self.waiting,
            "connected": self.connected,
            "capacity": self.capacity,
        }


def now_ts() -> float:
    return time.time()
