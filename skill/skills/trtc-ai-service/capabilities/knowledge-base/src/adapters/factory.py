"""adapter factory: selects KnowledgeBaseClient implementation based on environment variable.

Environment variable `KB_ADAPTER`:
    local_json    Default local JSON file search (production-ready, zero dependencies)
    mock          Built-in demo FAQ (for Recipe video recording)
    default_rest  Call remote FAQ service per business_contract default contract
    user_custom   User integration wizard generated implementation

When not set or invalid, fall back to local_json (keeps behavior compatibility with Phase 2).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from ..ports.kb_client import KnowledgeBaseClient


logger = logging.getLogger(__name__)


_VALID = ("local_json", "mock", "default_rest", "user_custom")


def _build(name: str) -> Optional[KnowledgeBaseClient]:
    if name == "local_json":
        from .local_json import from_env as build_local
        return build_local()
    if name == "mock":
        from .mock import from_env as build_mock
        return build_mock()
    if name == "default_rest":
        from .default_rest import from_env as build_rest
        c = build_rest()
        if c is None:
            logger.warning(
                "KB_ADAPTER=default_rest but KB_REST_BASE_URL is empty; "
                "falling back to local_json"
            )
        return c
    if name == "user_custom":
        try:
            from .user_custom import from_env as build_custom  # type: ignore
        except ImportError:
            logger.warning(
                "KB_ADAPTER=user_custom but src/adapters/user_custom.py is missing; "
                "run scripts/contract-adapt.py knowledge-base to generate it"
            )
            return None
        return build_custom()
    return None


def build_default() -> KnowledgeBaseClient:
    name = (os.getenv("KB_ADAPTER") or "local_json").strip().lower()
    if name not in _VALID:
        logger.warning("KB_ADAPTER=%s is not recognised; using local_json", name)
        name = "local_json"
    client = _build(name)
    if client is None:
        from .local_json import from_env as build_local
        client = build_local()
    return client


# ---------------------------------------------------------------------------
_singleton: Optional[KnowledgeBaseClient] = None


def get_client() -> KnowledgeBaseClient:
    global _singleton
    if _singleton is None:
        _singleton = build_default()
    return _singleton


def set_client(client: KnowledgeBaseClient) -> None:
    """For testing only: inject a custom client."""
    global _singleton
    _singleton = client


def reset_client() -> None:
    global _singleton
    _singleton = None
