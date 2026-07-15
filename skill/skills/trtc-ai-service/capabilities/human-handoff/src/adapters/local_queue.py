"""LocalQueueHandoffClient — default local implementation.

Zero external dependencies, in-process queuing + agent allocation. Migrated from the original queue.py implementation as the "default out-of-the-box" version.

Implementation notes:
- user_id also serves as ticket_id (keeping behavior consistent with old session_id)
- State machine:
    PENDING ──connect──▶ PROCESSING
       │  ▲                  │
       │  │                  ▼
     cancel/timeout       cancel/close
- Single-process RLock protection; cross-process sync handled by integrator upper layer (e.g. Redis)
- Capacity and agent count read from environment variables; can be overridden via constructor
"""
from __future__ import annotations

import os
import threading
from typing import Dict, List, Optional

from ..core.models import (
    OverallStatus,
    Ticket,
    TicketStatus,
    TicketStatusEnum,
    now_ts,
)
from ..ports.handoff_client import HandoffClient


class LocalQueueHandoffClient(HandoffClient):
    """In-process in-memory queuing HandoffClient implementation."""

    def __init__(
        self,
        *,
        capacity: int = 50,
        agent_pool_size: int = 1,
        estimated_wait_per_slot: int = 30,
    ) -> None:
        self._lock = threading.RLock()
        self._tickets: Dict[str, Ticket] = {}     # ticket_id -> Ticket
        self._waiting: List[str] = []             # ticket_id list, FIFO
        self._connected: Dict[str, str] = {}      # ticket_id -> agent_id
        self._capacity = int(capacity)
        self._pool = int(agent_pool_size)
        self._wait_per_slot = max(1, int(estimated_wait_per_slot))

    # ------------------------------------------------------------------
    # HandoffClient required implementations
    # ------------------------------------------------------------------
    def create_ticket(
        self,
        *,
        user_id: str,
        subject: str = "",
        description: str = "",
        priority: str = "normal",
        transcript: Optional[List[str]] = None,
    ) -> Ticket:
        if not user_id:
            raise ValueError("user_id is required")
        with self._lock:
            # Only one in-progress ticket per user; if exists, refresh position and return
            existing = self._find_active_by_user(user_id)
            if existing is not None:
                if existing.status == TicketStatusEnum.PROCESSING.value:
                    return existing
                self._refresh_position(existing)
                return existing

            ticket_id = user_id  # Compatible with old behavior: session_id is ticket_id
            t = Ticket(
                ticket_id=ticket_id,
                user_id=user_id,
                subject=subject,
                description=description,
                priority=priority or "normal",
                transcript=list(transcript or []),
                reason=description[:128] if description else "",
                created_at=now_ts(),
                updated_at=now_ts(),
            )

            # Queue full and no available agents: mark TIMEOUT
            if (
                len(self._waiting) >= self._capacity
                and self._available_agents() == 0
            ):
                t.status = TicketStatusEnum.TIMEOUT.value
                t.closed_at = now_ts()
                self._tickets[ticket_id] = t
                return t

            t.status = TicketStatusEnum.PENDING.value
            self._tickets[ticket_id] = t
            self._waiting.append(ticket_id)

            # Auto-connect if an agent is available
            if self._available_agents() > 0:
                self._auto_connect()
            self._refresh_position(t)
            return t

    def query_status(self, ticket_id: str) -> Optional[TicketStatus]:
        with self._lock:
            t = self._tickets.get(ticket_id)
            if t is None:
                return None
            return TicketStatus.from_ticket(t)

    def cancel_ticket(self, ticket_id: str, reason: str = "") -> Optional[Ticket]:
        with self._lock:
            t = self._tickets.get(ticket_id)
            if t is None:
                return None
            if t.status == TicketStatusEnum.PROCESSING.value:
                self._connected.pop(ticket_id, None)
            self._waiting = [s for s in self._waiting if s != ticket_id]
            t.status = TicketStatusEnum.CANCELED.value
            t.reason = reason or t.reason
            t.closed_at = now_ts()
            t.updated_at = now_ts()
            self._refresh_all_positions()
            return t

    def overall_status(self) -> OverallStatus:
        with self._lock:
            return OverallStatus(
                agent_pool_size=self._pool,
                available_agents=self._available_agents(),
                waiting=len(self._waiting),
                connected=len(self._connected),
                capacity=self._capacity,
            )

    # ------------------------------------------------------------------
    # Dashboard helper methods
    # ------------------------------------------------------------------
    def list_tickets(
        self,
        *,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> List[Ticket]:
        with self._lock:
            items = list(self._tickets.values())
            if status:
                items = [t for t in items if t.status == status]
            items.sort(
                key=lambda x: (x.created_at or 0.0),
                reverse=True,
            )
            return items[: max(1, int(limit))]

    def update_status(
        self,
        ticket_id: str,
        status: str,
        *,
        agent_id: Optional[str] = None,
    ) -> Optional[Ticket]:
        try:
            new_status = TicketStatusEnum(status).value
        except ValueError as exc:
            raise ValueError(f"invalid status: {status}") from exc

        with self._lock:
            t = self._tickets.get(ticket_id)
            if t is None:
                return None

            old_status = t.status
            t.status = new_status
            t.updated_at = now_ts()

            if new_status == TicketStatusEnum.PROCESSING.value:
                if old_status != TicketStatusEnum.PROCESSING.value:
                    if self._available_agents() <= 0 and ticket_id not in self._connected:
                        # Force connect (manual): open new slot outside agent pool
                        pass
                    t.agent_id = agent_id or t.agent_id or f"agent_{ticket_id[-4:]}"
                    self._connected[ticket_id] = t.agent_id
                    self._waiting = [s for s in self._waiting if s != ticket_id]
            elif new_status in (
                TicketStatusEnum.CLOSED.value,
                TicketStatusEnum.CANCELED.value,
                TicketStatusEnum.TIMEOUT.value,
            ):
                t.closed_at = now_ts()
                self._connected.pop(ticket_id, None)
                self._waiting = [s for s in self._waiting if s != ticket_id]
            elif new_status == TicketStatusEnum.PENDING.value:
                self._connected.pop(ticket_id, None)
                if ticket_id not in self._waiting:
                    self._waiting.append(ticket_id)

            self._refresh_all_positions()
            if self._available_agents() > 0:
                self._auto_connect()
            return t

    def get_or_attach(self, user_id: str) -> Optional[Ticket]:
        with self._lock:
            return self._find_active_by_user(user_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _available_agents(self) -> int:
        return max(0, self._pool - len(self._connected))

    def _find_active_by_user(self, user_id: str) -> Optional[Ticket]:
        for t in self._tickets.values():
            if t.user_id == user_id and t.status in (
                TicketStatusEnum.PENDING.value,
                TicketStatusEnum.PROCESSING.value,
            ):
                return t
        return None

    def _auto_connect(self) -> None:
        while self._waiting and self._available_agents() > 0:
            tid = self._waiting.pop(0)
            t = self._tickets.get(tid)
            if t is None:
                continue
            t.status = TicketStatusEnum.PROCESSING.value
            t.updated_at = now_ts()
            t.agent_id = f"agent_auto_{int(t.updated_at)}"
            self._connected[tid] = t.agent_id

    def _refresh_position(self, t: Ticket) -> None:
        if (
            t.status == TicketStatusEnum.PENDING.value
            and t.ticket_id in self._waiting
        ):
            pos = self._waiting.index(t.ticket_id) + 1
            t.queue_position = pos
            t.eta_seconds = pos * self._wait_per_slot
        else:
            t.queue_position = 0
            t.eta_seconds = 0

    def _refresh_all_positions(self) -> None:
        for t in self._tickets.values():
            self._refresh_position(t)


# ---------------------------------------------------------------------------
# Factory: build default parameters from environment variables
# ---------------------------------------------------------------------------
def from_env() -> LocalQueueHandoffClient:
    return LocalQueueHandoffClient(
        capacity=int(os.getenv("HH_QUEUE_CAPACITY", "50")),
        agent_pool_size=int(os.getenv("HH_AGENT_POOL_SIZE", "1")),
        estimated_wait_per_slot=int(os.getenv("HH_WAIT_PER_SLOT", "30")),
    )
