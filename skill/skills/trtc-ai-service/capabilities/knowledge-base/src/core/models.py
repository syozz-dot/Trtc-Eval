"""knowledge-base core models.

Defines unified domain models:
- FaqEntry  Knowledge entry (id / question / answer / keywords / source)
- SearchHit Search hit (with score)
- KbStats   Knowledge base statistics (entry count / data source type / load time)

All adapters must use this module's data structures as transport objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FaqEntry:
    """A single FAQ knowledge entry."""

    id: str
    question: str
    answer: str
    keywords: List[str] = field(default_factory=list)
    # Optional: annotate entry source (local_json / remote_api / user_uploaded etc.), useful for dashboard display
    source: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "keywords": list(self.keywords),
            **({"source": self.source} if self.source else {}),
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "FaqEntry":
        return cls(
            id=str(raw.get("id") or raw.get("question", ""))[:64] or "auto",
            question=str(raw.get("question", "")).strip(),
            answer=str(raw.get("answer", "")).strip(),
            keywords=[
                str(k).strip()
                for k in (raw.get("keywords") or [])
                if str(k).strip()
            ],
            source=raw.get("source"),
        )


@dataclass
class SearchHit:
    """Search hit."""

    entry: FaqEntry
    score: float

    def to_dict(self) -> dict:
        return {"entry": self.entry.to_dict(), "score": round(float(self.score), 4)}


@dataclass
class KbStats:
    """Knowledge base statistics (dashboard use)."""

    backend: str                    # "local_json" / "remote_api" / "mock" / "user_custom"
    entry_count: int
    loaded_at: Optional[float] = None
    data_source: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "entry_count": self.entry_count,
            "loaded_at": self.loaded_at,
            "data_source": self.data_source,
        }
