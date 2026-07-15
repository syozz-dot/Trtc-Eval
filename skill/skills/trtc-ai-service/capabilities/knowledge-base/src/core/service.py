"""KbService — Application service layer, combining KnowledgeBaseClient with instruction concatenation logic.

Only depends on ports (KnowledgeBaseClient interface); does not know the specific backend.
"""
from __future__ import annotations

from typing import List, Optional

from ..ports.kb_client import KnowledgeBaseClient
from .models import FaqEntry, KbStats, SearchHit


class KbService:

    def __init__(self, *, client: KnowledgeBaseClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
    ) -> List[SearchHit]:
        return self._client.search(query, top_k=top_k, min_score=min_score)

    def list_all(self) -> List[FaqEntry]:
        return self._client.list_all()

    def upsert(self, entry: FaqEntry) -> FaqEntry:
        return self._client.upsert(entry)

    def delete(self, entry_id: str) -> bool:
        return self._client.delete(entry_id)

    def stats(self) -> KbStats:
        return self._client.stats()

    def reload(self) -> int:
        return self._client.reload()

    # ------------------------------------------------------------------
    # For injection into conversation-core.before_start: concatenate search results into instructions
    # ------------------------------------------------------------------
    def attach_faq_to_instructions(
        self,
        instructions: str,
        *,
        max_hits: int = 3,
    ) -> str:
        if not instructions:
            return instructions
        hits = self._client.search(instructions, top_k=max_hits)
        if not hits:
            return instructions
        block = ["", "# Retrieved Knowledge (auto-injected by knowledge-base capability)"]
        for h in hits:
            block.append(f"- Q: {h.entry.question}")
            block.append(f"  A: {h.entry.answer}")
        return instructions + "\n" + "\n".join(block)


# ---------------------------------------------------------------------------
_default_service: Optional[KbService] = None


def get_default_service() -> KbService:
    global _default_service
    if _default_service is None:
        from ..adapters.factory import get_client
        _default_service = KbService(client=get_client())
    return _default_service


def reset_default_service() -> None:
    global _default_service
    _default_service = None
