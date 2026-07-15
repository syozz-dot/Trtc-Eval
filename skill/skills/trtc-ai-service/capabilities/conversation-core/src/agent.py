"""Voice Agent session orchestration (unified ASR / LLM / TTS / session management pipeline).

The skeleton only handles protocol orchestration:
1) Client obtains RoomId / user UserSig via /api/v1/get_config
2) Frontend SDK joins the room and calls /api/v1/agent/start
3) Server uses trtc_client.start() to launch the AI channel bot
   ↳ TRTC ConversationAI internally chains ASR → LLM → TTS full pipeline
4) /api/v1/agent/stop closes the task
5) /api/v1/agent/control is used for text injection / interrupt (covering text_input modality)

Note: This module does not introduce any business prompts, industry knowledge bases, or FAQ templates.
All business logic is overlaid via external capability packages using manifest.yaml injection points.
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, Optional

from .credentials import Credentials
from .modality import IoModality
from .trtc_client import AgentLifecycleConfig, TrtcConversationClient
from .usersig import gen_user_sig

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    session_id: str
    room_id: str
    user_id: str
    agent_user_id: str
    user_sig: str
    agent_user_sig: str
    task_id: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    request_id: Optional[str] = None


class ConversationAgent:
    """Voice Agent session manager.

    Singleton-style, instantiated and reused by server at startup. Only maintains in-memory
    session mapping, no persistence (production persistence handled by external capability packages).
    """

    def __init__(self, credentials: Credentials, io_modality: IoModality) -> None:
        if not credentials.fully_configured:
            raise ValueError(
                f"credentials missing: {credentials.missing()}; "
                "please run scripts/setup-credentials.py to complete configuration first"
            )
        self._cred = credentials
        self._io = io_modality
        self._client = TrtcConversationClient(
            tencent=credentials.tencent_cloud,
            trtc=credentials.trtc,
            llm=credentials.llm,
        )
        self._sessions: Dict[str, SessionInfo] = {}
        self._lock = RLock()

    # ------------------------------------------------------------------
    # /api/v1/get_config
    # ------------------------------------------------------------------
    def issue_config(
        self,
        user_id: Optional[str] = None,
        room_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate room credentials (room number / user UserSig / AI bot UserSig).

        Defaults to **numeric room IDs** (matching TRTC console default applications),
        avoiding ``InvalidParameter.UserSig`` false positives with apps that have
        PrivateMapKey disabled. UserId names use only ``[A-Za-z0-9_-]``, length ≤ 32 (TRTC hard constraint).
        """
        # Numeric room ID: random positive integer within 32-bit range
        room = str(room_id) if room_id else str(secrets.randbelow(2_000_000_000) + 1)
        u_id = str(user_id) if user_id else f"u_{secrets.token_hex(6)}"
        agent_u_id = f"ai_{secrets.token_hex(6)}"
        # TRTC UserId max length is 32; defensive truncation
        u_id = u_id[:32]
        agent_u_id = agent_u_id[:32]
        user_sig = gen_user_sig(
            sdk_app_id=self._cred.trtc.sdk_app_id,
            sdk_secret_key=self._cred.trtc.sdk_secret_key,
            user_id=u_id,
        )
        agent_sig = gen_user_sig(
            sdk_app_id=self._cred.trtc.sdk_app_id,
            sdk_secret_key=self._cred.trtc.sdk_secret_key,
            user_id=agent_u_id,
        )
        sid = secrets.token_urlsafe(12)
        info = SessionInfo(
            session_id=sid,
            room_id=room,
            user_id=u_id,
            agent_user_id=agent_u_id,
            user_sig=user_sig,
            agent_user_sig=agent_sig,
        )
        with self._lock:
            self._sessions[sid] = info
        logger.info("issue_config session=%s room=%s user=%s", sid, room, u_id)
        return {
            "session_id": sid,
            "sdk_app_id": self._cred.trtc.sdk_app_id,
            "room_id": room,
            "room_id_type": 0,  # Numeric room ID
            "user_id": u_id,
            "user_sig": user_sig,
            "agent_user_id": agent_u_id,
            "io_modality": self._io.to_dict(),
        }

    # ------------------------------------------------------------------
    # /api/v1/agent/start
    # ------------------------------------------------------------------
    def start_agent(
        self,
        session_id: str,
        config: Optional[AgentLifecycleConfig] = None,
    ) -> Dict[str, Any]:
        info = self._require_session(session_id)
        # _ext_before_start_  (capability extension anchor; do not remove)
        # Capabilities (e.g. knowledge-base) injected via add-capability.py land here,
        # inside the start_agent method body, where `config` and `info` are in scope.
        #
        # [knowledge-base] If knowledge-base capability is installed, prepend matched FAQ to instructions
        # via dynamic loading through _capability_loader, independent of cwd / repo directory name / hyphenated directories
        if config is not None and getattr(config, "instructions", None):
            from ._capability_loader import try_load_capability
            _kb = try_load_capability("knowledge-base", "src/retriever.py")
            if _kb is not None:
                try:
                    config.instructions = _kb.attach_faq_to_instructions(config.instructions)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("knowledge-base FAQ injection failed: %s", exc)
        result = self._client.start(
            room_id=info.room_id,
            agent_user_id=info.agent_user_id,
            agent_user_sig=info.agent_user_sig,
            target_user_id=info.user_id,
            config=config,
            room_id_type=0,  # Numeric room ID (consistent with issue_config)
        )
        with self._lock:
            info.task_id = result.get("task_id")
            info.request_id = result.get("request_id")
        logger.info("start_agent session=%s task=%s", session_id, info.task_id)
        # _ext_after_start_  (capability extension anchor; do not remove)
        # Capabilities (e.g. human-handoff) injected via add-capability.py land here,
        # inside the method body, where `session_id` and `info` are in scope.
        return {
            "session_id": session_id,
            "task_id": info.task_id,
            "request_id": info.request_id,
            "status": "started",
        }

    # ------------------------------------------------------------------
    # /api/v1/agent/stop
    # ------------------------------------------------------------------
    def stop_agent(self, session_id: str) -> Dict[str, Any]:
        info = self._require_session(session_id)
        if info.task_id:
            self._client.stop(info.task_id)
        with self._lock:
            self._sessions.pop(session_id, None)
        logger.info("stop_agent session=%s task=%s", session_id, info.task_id)
        return {"session_id": session_id, "status": "stopped"}

    # ------------------------------------------------------------------
    # /api/v1/agent/control
    # ------------------------------------------------------------------
    def push_text(
        self,
        session_id: str,
        text: str,
        interrupt: bool = True,
    ) -> Dict[str, Any]:
        """Text input channel: inject text into a running AI task."""
        info = self._require_session(session_id)
        if not info.task_id:
            raise RuntimeError("session has no active task; call start_agent first")
        if not text or not text.strip():
            raise ValueError("text cannot be empty")
        # _ext_before_push_text_  (capability extension anchor; do not remove)
        # Capabilities (human-handoff / tool-calling / session-summary) injected
        # via add-capability.py land here, inside push_text's body, where the
        # locals `session_id` and `text` are in scope.
        self._client.control(
            task_id=info.task_id,
            command="ServerPushText",
            text=text,
            interrupt=interrupt,
        )
        return {"session_id": session_id, "task_id": info.task_id, "delivered": True}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def list_sessions(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "sessions": [
                    {
                        "session_id": s.session_id,
                        "room_id": s.room_id,
                        "user_id": s.user_id,
                        "task_id": s.task_id,
                        "started_at": s.started_at,
                    }
                    for s in self._sessions.values()
                ]
            }

    def _require_session(self, session_id: str) -> SessionInfo:
        if not session_id:
            raise ValueError("session_id is required")
        with self._lock:
            info = self._sessions.get(session_id)
        if not info:
            raise ValueError(f"session not found: {session_id}")
        return info
