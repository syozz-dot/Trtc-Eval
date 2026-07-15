"""TRTC Conversational AI control plane client.

Encapsulates the minimal call chain for three REST APIs:
StartAIConversation / StopAIConversation / ControlAIConversation.
The skeleton layer only does "protocol encapsulation + credential signing",
with no built-in business prompts, industry knowledge bases, or FAQ templates.

API docs:
- StartAIConversation: https://cloud.tencent.com/document/product/647/108514
- StopAIConversation:  https://cloud.tencent.com/document/product/647/108513
- ControlAIConversation: https://cloud.tencent.com/document/product/647/109408
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

from .credentials import LlmCredential, TencentCloudCredential, TrtcCredential

logger = logging.getLogger(__name__)

_SERVICE = "trtc"
_VERSION = "2019-07-22"


def _sign_tc3(secret_key: str, date: str, string_to_sign: str) -> str:
    k_date = hmac.new(
        ("TC3" + secret_key).encode("utf-8"),
        date.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    k_service = hmac.new(k_date, _SERVICE.encode("utf-8"), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b"tc3_request", hashlib.sha256).digest()
    return hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()


def _signed_request(
    cred: TencentCloudCredential,
    host: str,
    region: str,
    action: str,
    payload: Dict[str, Any],
    timeout: float = 5.0,
) -> Dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    timestamp = int(time.time())
    date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")

    canonical_headers = (
        f"content-type:application/json; charset=utf-8\n"
        f"host:{host}\n"
        f"x-tc-action:{action.lower()}\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    hashed_payload = hashlib.sha256(body.encode("utf-8")).hexdigest()
    canonical_request = f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"
    credential_scope = f"{date}/{_SERVICE}/tc3_request"
    hashed_canonical = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = f"TC3-HMAC-SHA256\n{timestamp}\n{credential_scope}\n{hashed_canonical}"
    signature = _sign_tc3(cred.secret_key, date, string_to_sign)
    authorization = (
        f"TC3-HMAC-SHA256 Credential={cred.secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json; charset=utf-8",
        "Host": host,
        "X-TC-Action": action,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Version": _VERSION,
        "X-TC-Region": region,
    }
    resp = requests.post(
        f"https://{host}",
        headers=headers,
        data=body.encode("utf-8"),
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"TRTC API HTTP {resp.status_code}: {resp.text[:200]}")
    parsed = resp.json()
    response_obj = parsed.get("Response", {})
    err = response_obj.get("Error")
    request_id = response_obj.get("RequestId", "n/a")
    if err:
        raise RuntimeError(
            f"TRTC API error {err.get('Code')}: {err.get('Message')} "
            f"[endpoint={host}, action={action}, RequestId={request_id}]"
        )
    return response_obj


# Generic voice-assistant guardrails (NO industry/business assumptions).
#固化在骨架默认值里，确保：① 任何环境/任何 LLM 模型 ② 前端不传 instructions 时
# 都能避免 TTS 朗读 markdown 特殊符号，并让 AI 采信系统注入的权威上下文。
_DEFAULT_INSTRUCTIONS = (
    "You are a helpful voice assistant for an online store's customer service. "
    "Always answer in plain spoken language suitable for text-to-speech. "
    "Do NOT use any Markdown or formatting symbols such as asterisks (*), underscores (_), "
    "pound signs (#), backticks (`), tildes (~) or bullet / numbered-list markup, and never "
    "read such symbols aloud. "
    "Keep replies concise, ideally one to three sentences. "
    "For general questions such as product recommendations or shopping advice, answer helpfully "
    "and freely from your own knowledge — never claim you lack a product catalog or cannot help "
    "with general guidance; offer concrete, natural suggestions instead. "
    "Any information provided to you inside a message that begins with [system] is authoritative "
    "context: use it directly to answer the user, and never say you cannot find it or ask the user "
    "to repeat an identifier (such as an order number) that was already given to you."
)


@dataclass
class AgentLifecycleConfig:
    """Session lifecycle parameters (business-logic independent)."""

    instructions: str = _DEFAULT_INSTRUCTIONS
    greeting: str = "Hello, how can I help you?"
    max_idle_time: int = 60  # seconds
    welcome_message: str = ""
    language: str = "en"  # Default English (widest compatibility; Chinese requires TRTC app to enable corresponding capability)
    voice_id: str = "v-female-A4b9KqP2"  # TRTC FlowTTS default female voice (English Articulate Narrator)
    tts_model: str = "flow_01_turbo"


# TRTC FlowTTS verified voice IDs (taken from oral-coach project, confirmed working)
# Full voice list: https://trtc.io/document/79682?product=conversationalai
DEFAULT_VOICE_IDS = {
    ("en", "female"): "v-female-p9Xy7Q1L",  # Articulate Narrator
    ("en", "male"):   "v-male-A4b9KqP2",     # Scholarly Lecturer
    ("zh", "female"): "female-kefu-xiaoyue",
    ("zh", "male"):   "male-kefu-xiaoxu",
}


class TrtcConversationClient:
    """Thin wrapper around TRTC ConversationAI control plane.

    Constructor parameters:
        tencent: Tencent Cloud API keys (used to sign REST requests).
        trtc:    TRTC SDKAppID / SDKSecretKey (the SdkAppId in StartAIConversation).
        llm:     LLM credentials, used to populate LLMConfig (passthrough only, not called within the skeleton).
    """

    def __init__(
        self,
        tencent: TencentCloudCredential,
        trtc: TrtcCredential,
        llm: LlmCredential,
    ) -> None:
        if not tencent.configured:
            raise ValueError("tencent cloud credential not configured")
        if not trtc.configured:
            raise ValueError("trtc credential not configured")
        if not llm.configured:
            raise ValueError("llm credential not configured")
        self.tencent = tencent
        self.trtc = trtc
        self.llm = llm

    # ------------------------------------------------------------------
    # StartAIConversation
    # ------------------------------------------------------------------
    def start(
        self,
        room_id: str,
        agent_user_id: str,
        agent_user_sig: str,
        target_user_id: str,
        config: Optional[AgentLifecycleConfig] = None,
        room_id_type: int = 0,
    ) -> Dict[str, Any]:
        cfg = config or AgentLifecycleConfig()
        # Resolve voice_id: user explicit > default per language
        voice_id = cfg.voice_id or DEFAULT_VOICE_IDS.get(
            (cfg.language, "female"),
            DEFAULT_VOICE_IDS[("en", "female")],
        )
        payload: Dict[str, Any] = {
            "SdkAppId": self.trtc.sdk_app_id,
            "RoomId": str(room_id),
            "RoomIdType": room_id_type,
            "AgentConfig": {
                "UserId": agent_user_id,
                "UserSig": agent_user_sig,
                "MaxIdleTime": cfg.max_idle_time,
                "TargetUserId": target_user_id,
                "WelcomeMessage": cfg.welcome_message or cfg.greeting,
                # Smart interrupt (critical):
                #   InterruptMode 2 = auto + manual dual-track
                #     • Auto: user speaks beyond InterruptSpeechDuration ms → stop TTS
                #     • Manual: frontend sends type:20001 custom message → immediately stop TTS
                #       (for text input: send interrupt before text, then type:20000 triggers new turn)
                "InterruptMode": 2,
                "InterruptSpeechDuration": 500,
                # Subtitle mode: 1 = deliver both user and AI subtitles to client
                "SubtitleMode": 1,
                # Single-word filter: prevent ASR from splitting filler sounds like "um/ah" into single words
                "FilterOneWord": True,
                # Turn detection: 3 = semantic + VAD dual-signal to detect when user has finished speaking
                "TurnDetectionMode": 3,
                "TurnDetection": {"SemanticEagerness": "auto"},
            },
            "STTConfig": {
                "Language": cfg.language,
                "VadLevel": 3,
                "VadSilenceTime": 1000,
            },
            "LLMConfig": json.dumps(
                {
                    "LLMType": self.llm.llm_type,
                    "Model": self.llm.model,
                    "APIKey": self.llm.api_key,
                    "APIUrl": self.llm.api_url,
                    "Streaming": True,
                    "SystemPrompt": cfg.instructions,
                    "History": 20,
                    "Temperature": 0.4,
                },
                separators=(",", ":"),
                ensure_ascii=False,
            ),
            "TTSConfig": json.dumps(
                {
                    "TTSType": "flow",
                    "Model": cfg.tts_model,
                    "VoiceId": voice_id,
                    "Speed": 1.0,
                    "Volume": 1.0,
                    "Pitch": 0,
                    "Language": cfg.language,
                },
                separators=(",", ":"),
                ensure_ascii=False,
            ),
        }
        # Log key diagnostics before starting (UserSig redacted)
        logger.info(
            "StartAIConversation: endpoint=%s region=%s SdkAppId=%s RoomId=%s "
            "agent=%s target=%s userSig=%s...%s(len=%d) lang=%s voice=%s",
            self.trtc.trtc_endpoint,
            self.trtc.trtc_region,
            self.trtc.sdk_app_id,
            room_id,
            agent_user_id,
            target_user_id,
            agent_user_sig[:6],
            agent_user_sig[-4:],
            len(agent_user_sig),
            cfg.language,
            voice_id,
        )
        resp = _signed_request(
            self.tencent,
            host=self.trtc.trtc_endpoint,
            region=self.trtc.trtc_region,
            action="StartAIConversation",
            payload=payload,
            timeout=10.0,
        )
        return {
            "task_id": resp.get("TaskId"),
            "request_id": resp.get("RequestId"),
        }

    # ------------------------------------------------------------------
    # StopAIConversation
    # ------------------------------------------------------------------
    def stop(self, task_id: str) -> None:
        if not task_id:
            raise ValueError("task_id is required")
        _signed_request(
            self.tencent,
            host=self.trtc.trtc_endpoint,
            region=self.trtc.trtc_region,
            action="StopAIConversation",
            payload={"TaskId": task_id},
            timeout=5.0,
        )

    # ------------------------------------------------------------------
    # ControlAIConversation: used for text injection / interrupt
    # ------------------------------------------------------------------
    def control(
        self,
        task_id: str,
        command: str,
        text: Optional[str] = None,
        interrupt: bool = True,
    ) -> Dict[str, Any]:
        """Inject text or issue a control command to a running conversation task."""
        if not task_id or not command:
            raise ValueError("task_id and command are required")
        payload: Dict[str, Any] = {"TaskId": task_id, "Command": command}
        if text is not None:
            payload["ServerPushText"] = {
                "Text": text,
                "Interrupt": interrupt,
            }
        return _signed_request(
            self.tencent,
            host=self.trtc.trtc_endpoint,
            region=self.trtc.trtc_region,
            action="ControlAIConversation",
            payload=payload,
            timeout=5.0,
        )
