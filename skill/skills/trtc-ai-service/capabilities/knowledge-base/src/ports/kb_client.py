"""knowledge-base abstract port (Port).

Aligned with manifest.yaml.business_contract.external_apis:
- search   -> faq.search
- list_all -> faq.list
- upsert   -> faq.upsert
- delete   -> faq.delete

All concrete implementations (local_json / default_rest / mock / user_custom) must inherit this ABC.
The core layer only depends on this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ..core.models import FaqEntry, KbStats, SearchHit


class KnowledgeBaseClient(ABC):
    """Unified interface contract for knowledge base backends."""

    # ------------------------------------------------------------------
    # Aligned with business_contract
    # ------------------------------------------------------------------
    @abstractmethod
    def search(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
    ) -> List[SearchHit]:
        """Search for matching FAQ entries. Corresponds to business_contract.faq.search."""

    @abstractmethod
    def list_all(self) -> List[FaqEntry]:
        """List all entries. Corresponds to business_contract.faq.list."""

    @abstractmethod
    def upsert(self, entry: FaqEntry) -> FaqEntry:
        """Create or update a single entry. Corresponds to business_contract.faq.upsert."""

    @abstractmethod
    def delete(self, entry_id: str) -> bool:
        """Delete a single entry. Corresponds to business_contract.faq.delete."""

    # ------------------------------------------------------------------
    # Dashboard helper methods (default implementation; remote backends may not override)
    # ------------------------------------------------------------------
    def stats(self) -> KbStats:
        """Return statistics (defaults to live calculation based on list_all)."""
        items = self.list_all()
        return KbStats(
            backend=type(self).__name__,
            entry_count=len(items),
        )

    def reload(self) -> int:
        """Reload data from external source. Default no-op; local implementations can override to re-read files."""
        return len(self.list_all())
