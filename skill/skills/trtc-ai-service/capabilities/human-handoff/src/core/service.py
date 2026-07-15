"""HandoffService — Application service chaining IntentDetector with HandoffClient.

Only depends on ports (HandoffClient interface), does not know the specific backend implementation.
Switching adapter only requires re-injecting client (adapters.factory.set_client).
"""
from __future__ import annotations

from typing import List, Optional

from ..ports.handoff_client import HandoffClient
from ..summary_link import attach_summary_to_ticket
from .intent_detector import IntentDetector, get_default_detector
from .models import OverallStatus, Ticket, TicketStatus, TicketStatusEnum


class HandoffService:
    """Handoff business service."""

    def __init__(
        self,
        *,
        client: HandoffClient,
        detector: Optional[IntentDetector] = None,
    ) -> None:
        self._client = client
        self._detector = detector or get_default_detector()

    # ------------------------------------------------------------------
    # Intent detection + trigger (for injection into conversation-core.before_push_text)
    # ------------------------------------------------------------------
    def maybe_handoff(self, session_id: str, text: str) -> Optional[str]:
        """Recognize handoff intent; if matched, request ticket and return assembled script; otherwise return None."""
        if not session_id or not text:
            return None
        if not self._detector.is_handoff_intent(text):
            return None

        # Reuse existing ticket (don't duplicate for same user in progress)
        existing = self._client.get_or_attach(session_id)
        if existing is not None and existing.status in (
            TicketStatusEnum.PENDING.value,
            TicketStatusEnum.PROCESSING.value,
        ):
            return self._render_handoff_message(existing)

        ticket = self._client.create_ticket(
            user_id=session_id,
            subject=text[:64],
            description=text[:512],
            priority="normal",
        )
        # Attach session summary at ticket creation so agents can immediately see the issue on the dashboard (no-op if session-summary is not installed)
        attach_summary_to_ticket(ticket)
        return self._render_handoff_message(ticket)

    @staticmethod
    def _render_handoff_message(t: Ticket) -> Optional[str]:
        if t.status == TicketStatusEnum.PROCESSING.value:
            return (
                f"[handoff state=connected agent={t.agent_id}]\n"
                "You are now connected to a human agent. Please wait a moment."
            )
        if t.status == TicketStatusEnum.PENDING.value:
            return (
                f"[handoff state=waiting position={t.queue_position} "
                f"eta={t.eta_seconds}s]\n"
                f"You are number {t.queue_position} in the agent queue, "
                f"estimated wait {t.eta_seconds} seconds."
            )
        if t.status == TicketStatusEnum.TIMEOUT.value:
            return "[handoff state=timeout]\nNo agents are currently available. Please try again later."
        return None

    # ------------------------------------------------------------------
    # Explicit operations (for router calls)
    # ------------------------------------------------------------------
    def request(
        self,
        session_id: str,
        *,
        reason: str = "",
        subject: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Ticket:
        existing = self._client.get_or_attach(session_id)
        if existing is not None and existing.status in (
            TicketStatusEnum.PENDING.value,
            TicketStatusEnum.PROCESSING.value,
        ):
            return existing
        ticket = self._client.create_ticket(
            user_id=session_id,
            subject=(subject or reason or "human handoff")[:64],
            description=(description or reason or "")[:512],
            priority="normal",
        )
        # Attach session summary at ticket creation (no-op if session-summary not installed; does not affect main flow)
        attach_summary_to_ticket(ticket)
        return ticket

    def connect(self, session_id: str, agent_id: str) -> Ticket:
        """For /api/v1/handoff/connect: force-connect a session to a specified agent."""
        # Look up active ticket by user_id first
        ticket = self._client.get_or_attach(session_id)
        if ticket is None:
            raise ValueError(f"session {session_id} not waiting")
        if ticket.status == TicketStatusEnum.PROCESSING.value:
            return ticket
        updated = self._client.update_status(
            ticket.ticket_id,
            TicketStatusEnum.PROCESSING.value,
            agent_id=agent_id,
        )
        if updated is None:
            raise ValueError(f"ticket {ticket.ticket_id} not found")
        return updated

    def cancel(self, session_id: str, *, reason: str = "") -> Ticket:
        ticket = self._client.get_or_attach(session_id)
        if ticket is None:
            raise ValueError(f"session not found: {session_id}")
        result = self._client.cancel_ticket(ticket.ticket_id, reason=reason)
        if result is None:
            raise ValueError(f"ticket {ticket.ticket_id} not found")
        return result

    def get_by_session(self, session_id: str) -> Optional[Ticket]:
        return self._client.get_or_attach(session_id)

    def overall_status(self) -> OverallStatus:
        return self._client.overall_status()

    # ------------------------------------------------------------------
    # Dashboard helpers
    # ------------------------------------------------------------------
    def list_tickets(
        self,
        *,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> List[Ticket]:
        return self._client.list_tickets(limit=limit, status=status)

    def update_ticket_status(
        self,
        ticket_id: str,
        status: str,
        *,
        agent_id: Optional[str] = None,
    ) -> Optional[Ticket]:
        return self._client.update_status(ticket_id, status, agent_id=agent_id)

    def query_ticket(self, ticket_id: str) -> Optional[TicketStatus]:
        return self._client.query_status(ticket_id)

    # ------------------------------------------------------------------
    # Customer satisfaction feedback
    # ------------------------------------------------------------------
    def submit_feedback(self, session_id: str, rating: int, comment: str = "") -> dict:
        """Persist a satisfaction rating and, if a ticket exists for the session,
        attach it to that ticket so agents can see the score on the dashboard."""
        from ..feedback_store import make_feedback, save_feedback

        fb = make_feedback(rating, comment)
        save_feedback(session_id, fb)
        try:
            ticket = self._client.get_or_attach(session_id)
            if ticket is not None:
                ticket.extra["feedback"] = fb
        except Exception:  # noqa: BLE001 - feedback must never break on ticket lookup
            pass
        return {"session_id": session_id, "feedback": fb}


# ---------------------------------------------------------------------------
# Default service singleton
# ---------------------------------------------------------------------------
_default_service: Optional[HandoffService] = None


def get_default_service() -> HandoffService:
    """Build service singleton from current environment (client from adapters.factory)."""
    global _default_service
    if _default_service is None:
        from ..adapters.factory import get_client
        _default_service = HandoffService(client=get_client())
    return _default_service


def reset_default_service() -> None:
    global _default_service
    _default_service = None
