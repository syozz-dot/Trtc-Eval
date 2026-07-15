"""I/O modality configuration and degradation strategy (conversation-core built-in).

Four channels (voice input / voice output / text input / text output) are independently configurable.
When a channel service is unavailable, the system automatically degrades to an available channel
according to the strategy declared in this module, ensuring session continuity.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Channel(str, Enum):
    VOICE_INPUT = "voice_input"
    TEXT_INPUT = "text_input"
    VOICE_OUTPUT = "voice_output"
    TEXT_OUTPUT = "text_output"


@dataclass
class ChannelConfig:
    enabled: bool = True
    provider: Optional[str] = None
    fallback: Optional[Channel] = None
    timeout_ms: int = 0


@dataclass
class IoModality:
    voice_input: ChannelConfig = field(
        default_factory=lambda: ChannelConfig(
            enabled=True, provider="trtc-asr", fallback=Channel.TEXT_INPUT, timeout_ms=5000
        )
    )
    text_input: ChannelConfig = field(default_factory=lambda: ChannelConfig(enabled=True))
    voice_output: ChannelConfig = field(
        default_factory=lambda: ChannelConfig(
            enabled=True, provider="trtc-tts", fallback=Channel.TEXT_OUTPUT, timeout_ms=3000
        )
    )
    text_output: ChannelConfig = field(default_factory=lambda: ChannelConfig(enabled=True))

    def to_dict(self) -> dict:
        def _dump(c: ChannelConfig) -> dict:
            return {
                "enabled": c.enabled,
                "provider": c.provider,
                "fallback": c.fallback.value if c.fallback else None,
                "timeout_ms": c.timeout_ms,
            }

        return {
            Channel.VOICE_INPUT.value: _dump(self.voice_input),
            Channel.TEXT_INPUT.value: _dump(self.text_input),
            Channel.VOICE_OUTPUT.value: _dump(self.voice_output),
            Channel.TEXT_OUTPUT.value: _dump(self.text_output),
        }

    def resolve_input_channel(self, voice_available: bool) -> Channel:
        """Return the input channel to use, based on enabled status + service availability."""
        if self.voice_input.enabled and voice_available:
            return Channel.VOICE_INPUT
        if self.voice_input.fallback and self.text_input.enabled:
            return Channel.TEXT_INPUT
        if self.text_input.enabled:
            return Channel.TEXT_INPUT
        # Edge case: all input channels unavailable -> upper layer enters silent wait
        raise RuntimeError("no usable input channel")

    def resolve_output_channel(self, voice_available: bool) -> Channel:
        if self.voice_output.enabled and voice_available:
            return Channel.VOICE_OUTPUT
        if self.voice_output.fallback and self.text_output.enabled:
            return Channel.TEXT_OUTPUT
        if self.text_output.enabled:
            return Channel.TEXT_OUTPUT
        raise RuntimeError("no usable output channel")


def from_dict(data: dict) -> IoModality:
    """Construct IoModality instance from the io_modality section of manifest.yaml."""
    if not data:
        return IoModality()

    def _channel(value: Optional[str]) -> Optional[Channel]:
        if not value:
            return None
        return Channel(value)

    def _build(cfg: dict | None, default: ChannelConfig) -> ChannelConfig:
        if not cfg:
            return default
        return ChannelConfig(
            enabled=cfg.get("enabled", default.enabled),
            provider=cfg.get("provider", default.provider),
            fallback=_channel(cfg.get("fallback"))
            if "fallback" in cfg
            else default.fallback,
            timeout_ms=cfg.get("timeout_ms", default.timeout_ms),
        )

    base = IoModality()
    return IoModality(
        voice_input=_build(data.get("voice_input"), base.voice_input),
        text_input=_build(data.get("text_input"), base.text_input),
        voice_output=_build(data.get("voice_output"), base.voice_output),
        text_output=_build(data.get("text_output"), base.text_output),
    )
