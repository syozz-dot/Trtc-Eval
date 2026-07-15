"""human-handoff FastAPI sub-router.

Mounted on skeleton: app.include_router(router, prefix="/api/v1/handoff")

Refactoring notes:
- All business logic delegated to core.service.HandoffService
- Response fields remain fully consistent with Phase 2 (to_legacy_dict), not breaking Web Demo
- New /admin/* sub-routes for Phase 3 Path A ticket agent dashboard
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .core.models import TicketStatusEnum
from .core.service import get_default_service


router = APIRouter()


# ---------------------------------------------------------------------------
# Request body
# ---------------------------------------------------------------------------
class RequestBody(BaseModel):
    session_id: str = Field(..., max_length=64)
    reason: Optional[str] = Field(default="", max_length=512)


class ConnectBody(BaseModel):
    session_id: str = Field(..., max_length=64)
    agent_id: str = Field(..., max_length=64)


class CancelBody(BaseModel):
    session_id: str = Field(..., max_length=64)


class DetectBody(BaseModel):
    """Body for handoff intent detection (reuses intent_detector pure function)."""

    text: str = Field(..., max_length=4096)


class FeedbackBody(BaseModel):
    """Body for submitting a post-call satisfaction rating."""

    session_id: str = Field(..., max_length=64)
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(default="", max_length=1000)


class AdminUpdateBody(BaseModel):
    status: str = Field(..., max_length=32)
    agent_id: Optional[str] = Field(default=None, max_length=64)


# ---------------------------------------------------------------------------
# Existing endpoints (fully compatible with Phase 2)
# ---------------------------------------------------------------------------
@router.get("/status")
def overall() -> dict:
    return {"code": 0, "data": get_default_service().overall_status().to_dict()}


@router.get("/{session_id}")
def session_status(session_id: str) -> dict:
    ticket = get_default_service().get_by_session(session_id)
    if ticket is None:
        raise HTTPException(
            status_code=404, detail=f"session not tracked: {session_id}"
        )
    return {"code": 0, "data": ticket.to_legacy_dict()}


@router.post("/request")
def request_handoff(body: RequestBody) -> dict:
    ticket = get_default_service().request(
        body.session_id, reason=body.reason or ""
    )
    return {"code": 0, "data": ticket.to_legacy_dict()}


@router.post("/connect")
def connect(body: ConnectBody) -> dict:
    try:
        ticket = get_default_service().connect(body.session_id, body.agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"code": 0, "data": ticket.to_legacy_dict()}


@router.post("/cancel")
def cancel(body: CancelBody) -> dict:
    try:
        ticket = get_default_service().cancel(body.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "data": ticket.to_legacy_dict()}


# ---------------------------------------------------------------------------
# Intent detection + satisfaction feedback (issue 6 / issue 7)
# ---------------------------------------------------------------------------
@router.post("/detect")
def detect_handoff(body: DetectBody) -> dict:
    """Pure intent detection: returns whether the text implies a handoff request.

    Reuses core.intent_detector (same logic the backend uses internally), so the
    frontend fast-path and the backend stay in sync.
    """
    from .core.intent_detector import is_handoff_intent

    matched = bool(is_handoff_intent(body.text or ""))
    return {"code": 0, "data": {"matched": matched, "text": body.text or ""}}


@router.post("/feedback")
def submit_feedback(body: FeedbackBody) -> dict:
    """Persist a post-call CSAT rating and attach it to the session's ticket (if any)."""
    result = get_default_service().submit_feedback(
        body.session_id, body.rating, body.comment or ""
    )
    return {"code": 0, "data": result}


@router.get("/feedback/{session_id}")
def get_feedback(session_id: str) -> dict:
    """Return the stored feedback for a session (404 if not yet rated)."""
    from .feedback_store import get_feedback as _get

    fb = _get(session_id)
    if fb is None:
        raise HTTPException(
            status_code=404, detail=f"no feedback for session: {session_id}"
        )
    return {"code": 0, "data": {"session_id": session_id, "feedback": fb}}


# ---------------------------------------------------------------------------
# New: Ticket agent dashboard endpoints (Phase 3 Path A)
# Path: /admin/tickets
# These endpoints output "new version" fields (including ticket_id / subject / priority / transcript),
# coexisting with the legacy field format of existing /handoff/{session_id}.
# ---------------------------------------------------------------------------
@router.get("/admin/tickets")
def admin_list_tickets(
    limit: int = Query(default=50, ge=1, le=200),
    status: Optional[str] = Query(default=None, max_length=32),
) -> dict:
    items = get_default_service().list_tickets(limit=limit, status=status)
    return {
        "code": 0,
        "data": {
            "items": [t.to_dict() for t in items],
            "count": len(items),
        },
    }


@router.get("/admin/tickets/{ticket_id}")
def admin_get_ticket(ticket_id: str) -> dict:
    status = get_default_service().query_ticket(ticket_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"ticket not found: {ticket_id}")
    items = [
        t for t in get_default_service().list_tickets(limit=200)
        if t.ticket_id == ticket_id
    ]
    if not items:
        raise HTTPException(status_code=404, detail=f"ticket not found: {ticket_id}")
    return {"code": 0, "data": items[0].to_dict()}


@router.post("/admin/tickets/{ticket_id}/status")
def admin_update_status(ticket_id: str, body: AdminUpdateBody) -> dict:
    # Validate status value
    try:
        TicketStatusEnum(body.status)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"invalid status: {body.status}",
        ) from exc

    try:
        ticket = get_default_service().update_ticket_status(
            ticket_id, body.status, agent_id=body.agent_id
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=405, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if ticket is None:
        raise HTTPException(status_code=404, detail=f"ticket not found: {ticket_id}")
    return {"code": 0, "data": ticket.to_dict()}
