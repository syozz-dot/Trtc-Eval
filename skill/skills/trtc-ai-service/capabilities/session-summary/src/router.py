"""session-summary FastAPI sub-router."""
from __future__ import annotations

import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .recorder import get_recorder
from .summarizer import summarize

router = APIRouter()


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class TurnItem(BaseModel):
    role: str = Field(..., max_length=16)
    text: str = Field("", max_length=4096)


class RecordBody(BaseModel):
    """Batch-upload conversation turns so a summary can be attached to a ticket
    before the frontend requests a handoff."""

    turns: List[TurnItem] = Field(default_factory=list)


@router.get("/_list")
def list_recent(_offset: int = 0, _limit: int = 20) -> dict:
    if _limit < 1 or _limit > 200:
        raise HTTPException(status_code=400, detail="_limit out of range [1,200]")
    return {"code": 0, "data": get_recorder().list_recent(offset=_offset, limit=_limit)}


@router.get("/{session_id}")
def get_summary(session_id: str) -> dict:
    rec = get_recorder().get(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    return {"code": 0, "data": rec.to_dict()}


@router.post("/{session_id}/record")
def record_turns(session_id: str, body: RecordBody) -> dict:
    """Batch-record conversation turns for a session.

    Called by the frontend right before requesting a human handoff, so that
    attach_summary_to_ticket can produce a context summary from the transcript.
    Safe to call repeatedly; idempotent per turn text.
    """
    recorder = get_recorder()
    recorder.open(session_id)
    accepted = 0
    for t in body.turns:
        role = (t.role or "").strip().lower()
        if role not in ("user", "assistant", "system", "tool"):
            continue
        if not t.text:
            continue
        recorder.add_turn(session_id, role, t.text)
        accepted += 1
    rec = recorder.get(session_id)
    return {
        "code": 0,
        "data": {
            "session_id": session_id,
            "accepted": accepted,
            "total_turns": len(rec.turns) if rec else 0,
        },
    }


@router.post("/{session_id}/finalize")
def finalize(session_id: str) -> dict:
    rec = get_recorder().get(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    prefer_llm = os.getenv("SS_LLM_SUMMARY", "true").lower() == "true"
    summary = summarize(rec, prefer_llm=prefer_llm)
    rec = get_recorder().finalize(session_id, summary)
    # Write-back: select mock / local_json / default_rest by SS_ADAPTER (safe degradation to mock on failure)
    writeback = None
    try:
        from .adapters.factory import get_sink
        writeback = get_sink().write(rec.to_dict())
    except Exception as exc:  # noqa: BLE001
        writeback = {"accepted": False, "error": str(exc)}
    data = rec.to_dict()
    data["writeback"] = writeback
    return {"code": 0, "data": data}
