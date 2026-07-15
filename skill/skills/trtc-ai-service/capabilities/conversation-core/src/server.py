"""FastAPI entry point: exposes skeleton REST API + static Web Demo.

Routes:
  GET  /api/v1/health          —— Real-time connectivity check for 3 keys
  POST /api/v1/get_config      —— Generate RoomId / UserSig / modality config
  POST /api/v1/agent/start     —— Start AI conversation task
  POST /api/v1/agent/stop      —— Stop AI conversation task
  POST /api/v1/agent/control   —— Text injection / interrupt
  GET  /                       —— Web Demo static page

Design principles (aligned with §3.3):
  - Zero industry assumptions: all routes only do protocol orchestration, no built-in business prompts
  - Configuration as verification: health endpoint provides data source for Web Demo's three LEDs
  - Security compliance: log redaction filter installed at startup; credentials from env vars only
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

# Load .env before importing business modules to ensure credentials module reads correct env vars
_BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BASE_DIR / ".env.local")
load_dotenv(_BASE_DIR / ".env")

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import ConversationAgent
from .credentials import load_from_env
from .health import check_all
from .log_filter import install_redacting_filter
from .modality import IoModality
from .trtc_client import AgentLifecycleConfig

logger = logging.getLogger("conversation_core")

# Install log redaction filter (P0 security requirement)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
install_redacting_filter(logging.getLogger())


# ---------------------------------------------------------------------------
# Global Agent singleton (startup failure does not prevent /api/v1/health from giving clear diagnostics)
# ---------------------------------------------------------------------------
_credentials = load_from_env()
_io_modality = IoModality()  # Phase 1 default: all modalities enabled
_agent: Optional[ConversationAgent] = None
_init_error: Optional[str] = None
try:
    _agent = ConversationAgent(_credentials, _io_modality)
    logger.info("ConversationAgent initialized")
except Exception as exc:  # Credential missing etc. must not crash the process
    _init_error = str(exc)
    logger.warning("ConversationAgent not initialized: %s", _init_error)


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class GetConfigRequest(BaseModel):
    user_id: Optional[str] = None
    room_id: Optional[str] = None


class StartAgentRequest(BaseModel):
    session_id: str = Field(..., description="session_id returned by get_config")
    instructions: Optional[str] = None
    greeting: Optional[str] = None
    language: Optional[str] = "en"  # en | zh
    voice_id: Optional[str] = None  # Leave empty to use DEFAULT_VOICE_IDS selected by language
    max_idle_time: Optional[int] = 60


class StopAgentRequest(BaseModel):
    session_id: str


class ControlRequest(BaseModel):
    session_id: str
    text: str
    interrupt: bool = True


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="conversation-core",
    version="1.0.0",
    description="TRTC Voice Agent generic skeleton (no business assumptions)",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api/v1")


def _to_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail=f"internal: {exc}")


def _require_agent() -> ConversationAgent:
    if _agent is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "credentials_missing",
                "message": _init_error or "credentials not configured",
                "hint": "run scripts/setup-credentials.py first",
            },
        )
    return _agent


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@api.get("/health")
def health() -> Dict[str, Any]:
    """Real-time probe of 3 keys' connectivity, used by Web Demo top status bar."""
    cred = load_from_env()
    tc, trtc, llm = check_all(cred.tencent_cloud, cred.trtc, cred.llm)
    overall = "ok" if tc.ok and trtc.ok and llm.ok else "partial_failure"
    return {
        "status": overall,
        "checks": {
            "tencent_cloud": tc.to_dict(),
            "trtc": trtc.to_dict(),
            "llm": llm.to_dict(),
        },
        "configured": cred.fully_configured,
        "missing": cred.missing(),
        "io_modality": _io_modality.to_dict(),
    }


# ---------------------------------------------------------------------------
# Config / Lifecycle
# ---------------------------------------------------------------------------
@api.post("/get_config")
def get_config(req: GetConfigRequest) -> Dict[str, Any]:
    agent = _require_agent()
    try:
        data = agent.issue_config(user_id=req.user_id, room_id=req.room_id)
        return {"code": 0, "msg": "success", "data": data}
    except Exception as exc:
        raise _to_http_error(exc)


@api.post("/agent/start")
def agent_start(req: StartAgentRequest) -> Dict[str, Any]:
    agent = _require_agent()
    try:
        defaults = AgentLifecycleConfig()
        cfg = AgentLifecycleConfig(
            instructions=req.instructions or defaults.instructions,
            greeting=req.greeting or defaults.greeting,
            language=req.language or "en",
            voice_id=req.voice_id or "",
            max_idle_time=req.max_idle_time or 60,
        )
        return {"code": 0, "msg": "success", "data": agent.start_agent(req.session_id, cfg)}
    except Exception as exc:
        raise _to_http_error(exc)


@api.post("/agent/stop")
def agent_stop(req: StopAgentRequest) -> Dict[str, Any]:
    agent = _require_agent()
    try:
        return {"code": 0, "msg": "success", "data": agent.stop_agent(req.session_id)}
    except Exception as exc:
        raise _to_http_error(exc)


@api.post("/agent/control")
def agent_control(req: ControlRequest) -> Dict[str, Any]:
    agent = _require_agent()
    try:
        return {
            "code": 0,
            "msg": "success",
            "data": agent.push_text(req.session_id, req.text, req.interrupt),
        }
    except Exception as exc:
        raise _to_http_error(exc)


@api.get("/sessions")
def sessions_list() -> Dict[str, Any]:
    agent = _require_agent()
    return {"code": 0, "data": agent.list_sessions()}


# ---------------------------------------------------------------------------
# Debug endpoint: for troubleshooting InvalidParameter.UserSig etc.
# Outputs current config + a test UserSig for comparison against the TRTC official tool:
#   https://console.cloud.tencent.com/trtc/usersigtools
# Security: only returns SDKAppID / region / endpoint / test UserSig; never exposes plaintext SecretKey
# ---------------------------------------------------------------------------
@api.get("/debug/usersig")
def debug_usersig(user_id: str = "test_user_001") -> Dict[str, Any]:
    cred = load_from_env()
    if not cred.trtc.configured:
        raise HTTPException(status_code=503, detail="TRTC credential not configured")
    from .usersig import gen_user_sig

    sig = gen_user_sig(
        sdk_app_id=cred.trtc.sdk_app_id,
        sdk_secret_key=cred.trtc.sdk_secret_key,
        user_id=user_id,
        expire_seconds=86400,
    )
    return {
        "sdk_app_id": cred.trtc.sdk_app_id,
        "region": cred.trtc.region,
        "trtc_endpoint": cred.trtc.trtc_endpoint,
        "test_user_id": user_id,
        "test_user_sig": sig,
        "user_sig_length": len(sig),
        "verify_url": "https://console.cloud.tencent.com/trtc/usersigtools",
        "hint": (
            "Paste sdk_app_id / test_user_id / test_user_sig into the TRTC console official verification tool. "
            "If the tool shows UserSig verification passed → SDKSecretKey is correct; "
            "If the tool shows verification failed → the TRTC_SDK_SECRET_KEY you entered does not match this SDKAppID. "
            "Please re-check the SDKSecretKey in the TRTC console (note: this is NOT the Tencent Cloud API SecretKey)."
        ),
    }


app.include_router(api)
# [human-handoff] mount sub-router
from ._capability_loader import try_load_capability as _try_load_capability
_hh_router_mod = _try_load_capability("human-handoff", "src/router.py")
if _hh_router_mod is not None and hasattr(_hh_router_mod, "router"):
    app.include_router(
        _hh_router_mod.router, prefix="/api/v1/handoff", tags=["human-handoff"]
    )

# [session-summary] mount sub-router (default installed; supplies ticket context summaries)
_ss_router_mod = _try_load_capability("session-summary", "src/router.py")
if _ss_router_mod is not None and hasattr(_ss_router_mod, "router"):
    app.include_router(
        _ss_router_mod.router, prefix="/api/v1/summary", tags=["session-summary"]
    )

# ---------------------------------------------------------------------------
# Capability route mounting (optional; dynamically loaded via _capability_loader, silently
# skipped if the capability package is not installed).
# Injected by add-capability; all use try_load_capability to avoid hyphenated import failures.
# ---------------------------------------------------------------------------
from ._capability_loader import try_load_capability as _try_load_capability  # noqa: E402

# [knowledge-base] mount sub-router
_kb_router_mod = _try_load_capability("knowledge-base", "src/router.py")
if _kb_router_mod is not None and hasattr(_kb_router_mod, "router"):
    app.include_router(
        _kb_router_mod.router, prefix="/api/v1/kb", tags=["knowledge-base"]
    )


# ---------------------------------------------------------------------------
# Web Demo static pages (minimal verification page, no business content)
# Can point to a custom demo directory (e.g. Path A artifact directory) via
# the WEB_DEMO_DIR environment variable. Defaults to conversation-core's own web-demo self-check page.
# ---------------------------------------------------------------------------
_DEMO_DIR = Path(os.getenv("WEB_DEMO_DIR", str(_BASE_DIR / "web-demo")))
if _DEMO_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(_DEMO_DIR), html=True),
        name="static",
    )

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(str(_DEMO_DIR / "index.html"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "3000"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
