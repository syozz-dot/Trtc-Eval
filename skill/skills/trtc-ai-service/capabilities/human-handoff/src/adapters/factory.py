"""adapter factory: selects HandoffClient implementation based on environment variable.

Environment variable `HH_ADAPTER`:
    local_queue   Default local in-memory queue (production-ready, zero dependencies)
    mock          Demo data (includes several preset tickets for video recording)
    default_rest  Call remote ticketing system per business_contract default contract
    user_custom   User integration wizard (contract-adapt.py) generated implementation

When not set or invalid, fall back to local_queue (keeps behavior compatibility with Phase 2).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from ..ports.handoff_client import HandoffClient


logger = logging.getLogger(__name__)


_VALID = ("local_queue", "mock", "default_rest", "user_custom")


def _build(name: str) -> Optional[HandoffClient]:
    if name == "local_queue":
        from .local_queue import from_env as build_local
        return build_local()
    if name == "mock":
        from .mock import from_env as build_mock
        return build_mock()
    if name == "default_rest":
        from .default_rest import from_env as build_rest
        c = build_rest()
        if c is None:
            logger.warning(
                "HH_ADAPTER=default_rest but HH_REST_BASE_URL is empty; "
                "falling back to local_queue"
            )
        return c
    if name == "user_custom":
        try:
            from .user_custom import from_env as build_custom  # type: ignore
        except ImportError:
            logger.warning(
                "HH_ADAPTER=user_custom but src/adapters/user_custom.py is missing; "
                "run scripts/contract-adapt.py human-handoff to generate it"
            )
            return None
        return build_custom()
    return None


def build_default() -> HandoffClient:
    """Build default client from environment variables; invalid config falls back to local_queue."""
    name = (os.getenv("HH_ADAPTER") or "local_queue").strip().lower()
    if name not in _VALID:
        logger.warning("HH_ADAPTER=%s is not recognised; using local_queue", name)
        name = "local_queue"
    client = _build(name)
    if client is None:
        from .local_queue import from_env as build_local
        client = build_local()
    return client


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
_singleton: Optional[HandoffClient] = None


def get_client() -> HandoffClient:
    global _singleton
    if _singleton is None:
        _singleton = build_default()
    return _singleton


def set_client(client: HandoffClient) -> None:
    """For testing only: inject a custom client."""
    global _singleton
    _singleton = client


def reset_client() -> None:
    global _singleton
    _singleton = None
