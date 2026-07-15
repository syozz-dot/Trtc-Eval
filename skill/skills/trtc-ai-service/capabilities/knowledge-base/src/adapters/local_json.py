"""LocalJsonKbClient — default local implementation.

Zero external dependencies. Reads FAQ from JSON file + TF-IDF scoring. Migrated from the original retriever.py implementation as the "default out-of-the-box" version.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from ..core.models import FaqEntry, KbStats, SearchHit
from ..core.scoring import build_df, tfidf_score, tokenize
from ..ports.kb_client import KnowledgeBaseClient


class LocalJsonKbClient(KnowledgeBaseClient):
    """FAQ retriever based on local JSON file."""

    def __init__(
        self,
        data_file: Optional[str | Path] = None,
        *,
        min_score: float = 0.1,
        top_k: int = 3,
    ) -> None:
        self._lock = threading.RLock()
        self._entries: List[FaqEntry] = []
        self._df: Dict[str, int] = {}
        self._min_score = float(min_score)
        self._top_k = int(top_k)
        self._data_file: Optional[Path] = (
            Path(data_file) if data_file else None
        )
        self._loaded_at: Optional[float] = None
        if self._data_file and self._data_file.exists():
            self.reload()

    # ------------------------------------------------------------------
    # KnowledgeBaseClient required implementations
    # ------------------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
    ) -> List[SearchHit]:
        if not query or not query.strip():
            return []
        k = top_k or self._top_k
        threshold = float(min_score) if min_score is not None else self._min_score
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        with self._lock:
            n = max(1, len(self._entries))
            hits: List[SearchHit] = []
            for entry in self._entries:
                score = tfidf_score(entry, q_tokens, df=self._df, n_docs=n)
                if score >= threshold:
                    hits.append(SearchHit(entry=entry, score=score))
            hits.sort(key=lambda h: h.score, reverse=True)
            return hits[:k]

    def list_all(self) -> List[FaqEntry]:
        with self._lock:
            return [
                FaqEntry(
                    id=e.id,
                    question=e.question,
                    answer=e.answer,
                    keywords=list(e.keywords),
                    source=e.source or "local_json",
                )
                for e in self._entries
            ]

    def upsert(self, entry: FaqEntry) -> FaqEntry:
        if not entry.id or not entry.question:
            raise ValueError("id and question are required")
        with self._lock:
            for i, e in enumerate(self._entries):
                if e.id == entry.id:
                    self._entries[i] = entry
                    self._rebuild_df()
                    self._persist()
                    return entry
            self._entries.append(entry)
            self._rebuild_df()
            self._persist()
            return entry

    def delete(self, entry_id: str) -> bool:
        with self._lock:
            before = len(self._entries)
            self._entries = [e for e in self._entries if e.id != entry_id]
            removed = before != len(self._entries)
            if removed:
                self._rebuild_df()
                self._persist()
            return removed

    def stats(self) -> KbStats:
        with self._lock:
            return KbStats(
                backend="local_json",
                entry_count=len(self._entries),
                loaded_at=self._loaded_at,
                data_source=str(self._data_file) if self._data_file else None,
            )

    def reload(self) -> int:
        if not self._data_file or not self._data_file.exists():
            return 0
        raw = json.loads(self._data_file.read_text(encoding="utf-8"))
        with self._lock:
            self._entries = [FaqEntry.from_dict(item) for item in raw]
            for e in self._entries:
                e.source = e.source or "local_json"
            self._rebuild_df()
            self._loaded_at = time.time()
        return len(self._entries)

    # ------------------------------------------------------------------
    @property
    def data_file(self) -> Optional[Path]:
        return self._data_file

    @property
    def min_score(self) -> float:
        return self._min_score

    @property
    def top_k(self) -> int:
        return self._top_k

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _rebuild_df(self) -> None:
        self._df = build_df(self._entries)

    def _persist(self) -> None:
        if not self._data_file:
            return
        # Ensure directory exists
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._data_file.with_suffix(self._data_file.suffix + ".tmp")
        tmp.write_text(
            json.dumps(
                [e.to_dict() for e in self._entries],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(tmp, self._data_file)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def from_env() -> LocalJsonKbClient:
    default_file = Path(__file__).resolve().parent.parent.parent / "data" / "faq.json"
    return LocalJsonKbClient(
        data_file=os.getenv("KB_DATA_FILE", str(default_file)),
        min_score=float(os.getenv("KB_MIN_SCORE", "0.1")),
        top_k=int(os.getenv("KB_TOP_K", "3")),
    )
