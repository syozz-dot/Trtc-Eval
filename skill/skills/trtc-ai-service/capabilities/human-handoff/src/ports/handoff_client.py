"""human-handoff abstract port (Port).

One-to-one correspondence with manifest.yaml.business_contract fields:
- create_ticket   -> ticket.create
- query_status    -> ticket.status_query
- cancel_ticket   -> ticket.cancel
- overall_status  -> internal status (not in external contract; for local dashboard use only)

All concrete implementations (local_queue / default_rest / mock / user_custom) must inherit this ABC.
The core layer only depends on this interface, unaware of any specific backend type; switching backends only requires changing the adapter.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ..core.models import OverallStatus, Ticket, TicketStatus


class HandoffClient(ABC):
    """Unified interface contract for handoff / ticketing backends."""

    # --- Methods aligned with business_contract --------------------------

    @abstractmethod
    def create_ticket(
        self,
        *,
        user_id: str,
        subject: str = "",
        description: str = "",
        priority: str = "normal",
        transcript: Optional[List[str]] = None,
    ) -> Ticket:
        """Create ticket. Corresponds to business_contract.ticket.create."""

    @abstractmethod
    def query_status(self, ticket_id: str) -> Optional[TicketStatus]:
        """Query single ticket status. Corresponds to ticket.status_query.

        Returns None if ticket does not exist.
        """

    @abstractmethod
    def cancel_ticket(self, ticket_id: str, reason: str = "") -> Optional[Ticket]:
        """Cancel ticket. Corresponds to ticket.cancel. Returns None if ticket does not exist."""

    @abstractmethod
    def overall_status(self) -> OverallStatus:
        """Overall queue status (dashboard use, not external contract)."""

    # --- Dashboard helper methods (default implementation; remote backends may not override) ---------

    def list_tickets(
        self,
        *,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> List[Ticket]:
        """List tickets (default returns empty; remote backends override as needed)."""
        return []

    def update_status(
        self,
        ticket_id: str,
        status: str,
        *,
        agent_id: Optional[str] = None,
    ) -> Optional[Ticket]:
        """Agent manually updates ticket status (not supported by default; can be overridden by mock / local_queue)."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support manual status update"
        )

    # --- Bridge interface compatible with old trigger.maybe_handoff ---------

    def get_or_attach(self, user_id: str) -> Optional[Ticket]:
        """Find existing ticket by user_id (old session_id); returns None if not found.

        This method allows the facade layer to query existing ticket status without breaking the old API.
        Default implementation iterates list_tickets.
        """
        for t in self.list_tickets(limit=200):
            if t.user_id == user_id:
                return t
        return None
