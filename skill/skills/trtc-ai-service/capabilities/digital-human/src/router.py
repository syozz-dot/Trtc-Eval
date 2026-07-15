"""digital-human FastAPI placeholder router.

Interface contract fixed:
- GET  /status    Returns placeholder status + roadmap
- POST /render    Returns 501 Not Implemented, deferred to future iterations
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/status")
def status() -> dict:
    return {
        "code": 0,
        "data": {
            "enabled": os.getenv("DH_ENABLED", "false").lower() == "true",
            "avatar_id": os.getenv("DH_AVATAR_ID", ""),
            "lipsync_provider": os.getenv("DH_LIPSYNC_PROVIDER", "tencent-cloud-vmp"),
            "expression_provider": os.getenv("DH_EXPRESSION_PROVIDER", "internal-rule"),
            "phase": "placeholder",
            "roadmap": [
                "Phase 3+: Integrate third-party rendering SDK (avatar / lipsync / expression)",
                "Support WebRTC datachannel driver data push",
            ],
        },
    }


@router.post("/render")
def render() -> dict:
    raise HTTPException(
        status_code=501,
        detail={
            "code": "not_implemented",
            "message": "digital-human render is a placeholder; rendering layer not shipped in Phase 2",
            "hint": "follow capabilities/digital-human/README.md for integration roadmap",
        },
    )
