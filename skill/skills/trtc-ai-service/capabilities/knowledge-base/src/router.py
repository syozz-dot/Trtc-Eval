"""knowledge-base FastAPI sub-router.

Mounted on skeleton: app.include_router(router, prefix="/api/v1/kb")

Refactoring notes:
- All business logic delegated to core.service.KbService
- Response fields remain fully consistent with Phase 2 (using SearchHit.to_dict / FaqEntry.to_dict)
"""
from __future__ import annotations

import re
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .core.models import FaqEntry
from .core.service import get_default_service


router = APIRouter()


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _HTML_TAG_RE.sub("", s).strip()


class UpsertRequest(BaseModel):
    id: str = Field(..., max_length=64)
    question: str = Field(..., max_length=1024)
    answer: str = Field(..., max_length=4096)
    keywords: List[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str = Field(..., max_length=256)
    top_k: Optional[int] = Field(default=None, ge=1, le=20)


@router.get("/list")
def list_entries() -> dict:
    items = get_default_service().list_all()
    return {"code": 0, "data": [e.to_dict() for e in items]}


@router.post("/search")
def search(req: SearchRequest) -> dict:
    hits = get_default_service().search(req.query, top_k=req.top_k)
    return {"code": 0, "data": [h.to_dict() for h in hits]}


@router.post("/upsert")
def upsert(req: UpsertRequest) -> dict:
    entry = FaqEntry(
        id=req.id.strip(),
        question=_strip_html(req.question),
        answer=_strip_html(req.answer),
        keywords=[_strip_html(k) for k in (req.keywords or []) if k.strip()],
    )
    if not entry.id or not entry.question:
        raise HTTPException(status_code=400, detail="id and question are required")
    saved = get_default_service().upsert(entry)
    return {"code": 0, "data": saved.to_dict()}


@router.delete("/{entry_id}")
def delete(entry_id: str) -> dict:
    ok = get_default_service().delete(entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"entry not found: {entry_id}")
    return {"code": 0, "data": {"deleted": entry_id}}


@router.post("/reload")
def reload_data() -> dict:
    n = get_default_service().reload()
    return {"code": 0, "data": {"count": n}}


@router.get("/stats")
def stats() -> dict:
    return {"code": 0, "data": get_default_service().stats().to_dict()}
