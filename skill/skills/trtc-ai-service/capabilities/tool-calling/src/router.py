"""tool-calling FastAPI sub-router."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .registry import get_loader

router = APIRouter()


class InvokeRequest(BaseModel):
    name: str = Field(..., max_length=64)
    params: Dict[str, Any] = Field(default_factory=dict)
    priority: Optional[str] = Field(default=None, pattern="^(alpha|beta|manifest_order)$")


@router.get("/list")
def list_tools() -> dict:
    return {"code": 0, "data": get_loader().list_tools()}


@router.post("/invoke")
def invoke(req: InvokeRequest) -> dict:
    result = get_loader().call(req.name, req.params, priority=req.priority)
    if not result.ok:
        # 200 + ok=false or 502? Here we use 200; caller judges by ok field; beta network errors use 502
        if result.track == "beta" and "Connection" in (result.error or ""):
            raise HTTPException(status_code=502, detail=result.error)
    return {
        "code": 0 if result.ok else 1,
        "msg": "success" if result.ok else result.error,
        "data": {
            "tool": result.tool,
            "track": result.track,
            "ok": result.ok,
            "output": result.output,
            "error": result.error,
            "latency_ms": result.latency_ms,
            "fallback_chain": result.fallback_chain,
        },
    }


@router.post("/reload")
def reload_registry() -> dict:
    n = get_loader().reload()
    return {"code": 0, "data": {"count": n}}
