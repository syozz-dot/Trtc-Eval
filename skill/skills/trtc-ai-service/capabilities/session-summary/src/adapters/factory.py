"""Write-back sink factory — selects implementation by env SS_ADAPTER (consistent with KB/handoff factory paradigm).

    SS_ADAPTER=mock         Default; no external dependencies
    SS_ADAPTER=local_json   Write local JSONL
    SS_ADAPTER=default_rest POST to real CRM (requires SS_REST_BASE_URL)

When any implementation initialization fails (e.g. default_rest missing base_url), safely degrades to mock,
ensuring the finalize flow is never interrupted due to unavailable write-back targets.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from .base import SummarySink
from .mock import MockSink

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_instance: Optional[SummarySink] = None
_instance_key: Optional[str] = None


def _build(name: str) -> SummarySink:
    name = (name or "mock").strip().lower()
    if name == "local_json":
        from .local_json import LocalJsonSink
        return LocalJsonSink()
    if name == "default_rest":
        from .default_rest import DefaultRestSink
        return DefaultRestSink()
    return MockSink()


def get_sink() -> SummarySink:
    """Return the currently configured write-back sink (cached by SS_ADAPTER; rebuilds on env change)."""
    global _instance, _instance_key
    key = (os.getenv("SS_ADAPTER", "mock") or "mock").strip().lower()
    with _lock:
        if _instance is not None and _instance_key == key:
            return _instance
        try:
            _instance = _build(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("session-summary sink '%s' init failed, fallback to mock: %s", key, exc)
            _instance = MockSink()
        _instance_key = key
        return _instance
