"""retriever.py — compatibility facade.

Keeps the original `attach_faq_to_instructions` / `get_retriever` / `FaqEntry` / `SearchHit`
public symbols for manifest.extensions (agent.before_start) and external callers to continue using.

New code should use directly:
- adapters.factory.get_client()        Get KnowledgeBaseClient instance
- core.service.get_default_service()   Get KbService instance
"""
from __future__ import annotations

import warnings

from .core.models import FaqEntry, SearchHit  # noqa: F401  (public API)
from .core.service import get_default_service


def attach_faq_to_instructions(instructions: str) -> str:
    """For use by conversation-core.before_start injection point.

    Keeps old signature: single instructions parameter, returns concatenated instructions.
    """
    return get_default_service().attach_faq_to_instructions(instructions)


# --------------------------------------------------------------------
# Deprecated shim: original FaqRetriever global instance / class
# --------------------------------------------------------------------
def get_retriever():
    """[DEPRECATED] Return KnowledgeBaseClient instance.

    Old FaqRetriever class method names (list_entries/upsert/delete/search/reload)
    have corresponding methods on the new client (list_all/upsert/delete/search/reload),
    though some signatures differ slightly (list_entries -> list_all).
    """
    warnings.warn(
        "knowledge_base.retriever.get_retriever() is deprecated; "
        "use adapters.factory.get_client() or core.service.get_default_service() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from .adapters.factory import get_client
    return get_client()


# Legacy alias
FaqRetriever = "FaqRetriever (deprecated; use adapters.local_json.LocalJsonKbClient)"


__all__ = [
    "FaqEntry",
    "FaqRetriever",
    "SearchHit",
    "attach_faq_to_instructions",
    "get_retriever",
]
