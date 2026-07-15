"""MockHandoffClient — mock implementation for Recipe demo recording.

Inherits LocalQueueHandoffClient, pre-seeds several sample tickets on startup so the agent dashboard has content immediately.

Differences from LocalQueueHandoffClient:
- Seeds example tickets at construction (one each for pending / processing / closed)
- Marks `is_mock = True`, making it easy to add a "demo data" watermark on the dashboard
- Demo data uses stable ticket_id prefix `demo_` for reproducible screenshots
"""
from __future__ import annotations

from typing import List, Optional

from ..core.models import Ticket, TicketStatusEnum, now_ts
from .local_queue import LocalQueueHandoffClient


class MockHandoffClient(LocalQueueHandoffClient):
    """Mock implementation for demos."""

    is_mock = True

    def __init__(
        self,
        *,
        capacity: int = 50,
        agent_pool_size: int = 2,
        estimated_wait_per_slot: int = 30,
        seed_demo_data: bool = True,
    ) -> None:
        super().__init__(
            capacity=capacity,
            agent_pool_size=agent_pool_size,
            estimated_wait_per_slot=estimated_wait_per_slot,
        )
        if seed_demo_data:
            self._seed()

    def _seed(self) -> None:
        """Seed demo data. Agent pool occupies 1 slot, leaving 1 free for live connection demos."""
        ts_base = now_ts() - 600

        # 1) Closed ticket (10 minutes ago)
        closed = Ticket(
            ticket_id="demo_closed_001",
            user_id="demo_user_001",
            subject="Invoice header correction",
            description="Shipped order needs invoice header correction",
            priority="normal",
            status=TicketStatusEnum.CLOSED.value,
            agent_id="agent_alice",
            transcript=[
                "User: Hi, I need to update the invoice header",
                "AI: Which order is this regarding?",
                "User: Order number SO20260601-0042",
                "[handoff] User requested human agent",
                "Agent Alice: Done. New invoice will be issued within 30 minutes.",
            ],
            reason="Invoice header correction",
            created_at=ts_base,
            updated_at=ts_base + 120,
            closed_at=ts_base + 240,
        )
        self._tickets[closed.ticket_id] = closed

        # 2) Processing ticket (occupies 1 agent slot)
        processing = Ticket(
            ticket_id="demo_processing_001",
            user_id="demo_user_002",
            subject="Return logistics issue",
            description="Return not picked up for 5 days",
            priority="high",
            status=TicketStatusEnum.PROCESSING.value,
            agent_id="agent_bob",
            transcript=[
                "User: My return has been requested 5 days and no one has picked it up yet",
                "AI: Let me check the logistics status for you...",
                "AI: Sorry, the logistics API is temporarily unavailable for real-time info",
                "[handoff] Escalating to human agent",
                "Agent Bob: Hello, I am following up on your logistics issue",
            ],
            reason="Return logistics issue",
            created_at=ts_base + 300,
            updated_at=ts_base + 320,
        )
        self._tickets[processing.ticket_id] = processing
        self._connected[processing.ticket_id] = processing.agent_id  # type: ignore[assignment]

        # 3) Pending ticket (FIFO queue head)
        pending = Ticket(
            ticket_id="demo_pending_001",
            user_id="demo_user_003",
            subject="Refund progress inquiry",
            description="Refund applied 3 days ago not received",
            priority="normal",
            status=TicketStatusEnum.PENDING.value,
            transcript=[
                "User: My refund from 3 days ago hasn't arrived yet",
                "AI: Please provide your order number for lookup",
                "User: Order SO20260605-0099",
                "[handoff] Transfer to agent",
            ],
            reason="Refund progress",
            created_at=ts_base + 540,
            updated_at=ts_base + 540,
        )
        self._tickets[pending.ticket_id] = pending
        self._waiting.append(pending.ticket_id)
        self._refresh_all_positions()

    def list_tickets(
        self,
        *,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> List[Ticket]:
        # Mock mode defaults to reverse chrono by creation time, consistent with LocalQueue behavior
        return super().list_tickets(limit=limit, status=status)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def from_env() -> MockHandoffClient:
    import os

    return MockHandoffClient(
        capacity=int(os.getenv("HH_QUEUE_CAPACITY", "50")),
        agent_pool_size=int(os.getenv("HH_AGENT_POOL_SIZE", "2")),
        estimated_wait_per_slot=int(os.getenv("HH_WAIT_PER_SLOT", "30")),
        seed_demo_data=os.getenv("HH_MOCK_SEED", "1") not in ("0", "false", "False"),
    )
