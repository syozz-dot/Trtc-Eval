"""3-Key credential reading and encapsulation.

Credentials come only from environment variables (P0 Secrets spec: env-only); never
read from code or configuration files in plain text. After reading, they are exposed
to upper layers as dataclasses. Callers should not log the entire object — instead,
rely on log_filter.RedactingFilter for fallback redaction.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TencentCloudCredential:
    """Key 1: Tencent Cloud API keys (used for STS / TRTC control plane REST calls)."""

    secret_id: str
    secret_key: str
    region: str = "ap-guangzhou"

    @property
    def configured(self) -> bool:
        return bool(self.secret_id and self.secret_key)


@dataclass(frozen=True)
class TrtcCredential:
    """Key 2: TRTC Conversational AI application credentials.

    SDKAppID and SDKSecretKey are used to generate UserSig and call ConversationAI.
    region determines whether to call the international or China endpoint:
      - "intl" → Application registered at https://console.trtc.io (default)
      - "cn"   → Application registered at the China-region TRTC console
    """

    sdk_app_id: int
    sdk_secret_key: str
    region: str = "intl"  # intl | cn

    @property
    def configured(self) -> bool:
        return bool(self.sdk_app_id and self.sdk_secret_key)

    @property
    def trtc_endpoint(self) -> str:
        return (
            "trtc.intl.tencentcloudapi.com"
            if self.region == "intl"
            else "trtc.tencentcloudapi.com"
        )

    @property
    def trtc_region(self) -> str:
        return "ap-singapore" if self.region == "intl" else "ap-guangzhou"


@dataclass(frozen=True)
class LlmCredential:
    """Key 3: External LLM access key (OpenAI-compatible protocol)."""

    api_key: str
    api_url: str = "https://api.openai.com/v1/chat/completions"
    model: str = "gpt-4o-mini"
    llm_type: str = "openai"

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_url and self.model)


@dataclass(frozen=True)
class Credentials:
    """3-Key aggregate container."""

    tencent_cloud: TencentCloudCredential
    trtc: TrtcCredential
    llm: LlmCredential

    @property
    def fully_configured(self) -> bool:
        return all(
            (
                self.tencent_cloud.configured,
                self.trtc.configured,
                self.llm.configured,
            )
        )

    def missing(self) -> list[str]:
        miss: list[str] = []
        if not self.tencent_cloud.configured:
            miss.append("tencent_cloud")
        if not self.trtc.configured:
            miss.append("trtc")
        if not self.llm.configured:
            miss.append("llm")
        return miss


def _int_env(key: str, default: int = 0) -> int:
    raw = os.getenv(key, "")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def load_from_env() -> Credentials:
    """Load the 3 keys from environment variables.

    All key names match .env.example / setup-credentials.py output.
    """
    return Credentials(
        tencent_cloud=TencentCloudCredential(
            secret_id=os.getenv("TENCENT_CLOUD_SECRET_ID", ""),
            secret_key=os.getenv("TENCENT_CLOUD_SECRET_KEY", ""),
            region=os.getenv("TENCENT_CLOUD_REGION", "ap-guangzhou"),
        ),
        trtc=TrtcCredential(
            sdk_app_id=_int_env("TRTC_SDK_APP_ID", 0),
            sdk_secret_key=os.getenv("TRTC_SDK_SECRET_KEY", ""),
            region=os.getenv("TRTC_REGION", "intl"),
        ),
        llm=LlmCredential(
            api_key=os.getenv("LLM_API_KEY", ""),
            api_url=os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions"),
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            llm_type=os.getenv("LLM_TYPE", "openai"),
        ),
    )
