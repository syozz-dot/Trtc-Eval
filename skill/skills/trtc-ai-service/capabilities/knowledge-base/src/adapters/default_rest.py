"""DefaultRestKbClient — call external FAQ / search API per business_contract default contract.

Corresponding contracts:
- POST   /faq/search             faq.search
- GET    /faq                    faq.list
- POST   /faq                    faq.upsert
- DELETE /faq/{entry_id}         faq.delete

Environment variables:
- KB_REST_BASE_URL    FAQ service base URL
- KB_REST_TOKEN       Bearer Token (optional)
- KB_REST_TIMEOUT_MS  Timeout (default 5000)

Security: consistent with human-handoff default_rest — only https / localhost; reject private networks.
"""
from __future__ import annotations

import logging
import os
import re
from typing import List, Optional
from urllib.parse import urlparse

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from ..core.models import FaqEntry, KbStats, SearchHit
from ..ports.kb_client import KnowledgeBaseClient


logger = logging.getLogger(__name__)


_PRIVATE_PATTERNS = [
    re.compile(r"^9\."),
    re.compile(r"^10\."),
    re.compile(r"^11\."),
    re.compile(r"^21\."),
    re.compile(r"^30\."),
    re.compile(r"^169\.254\."),
    re.compile(r"^172\.(1[6-9]|2[0-9]|3[01])\."),
    re.compile(r"^192\.168\."),
]


def _is_localhost(host: str) -> bool:
    return host in {"localhost", "127.0.0.1", "::1"}


def _is_private(host: str) -> bool:
    return any(p.match(host) for p in _PRIVATE_PATTERNS)


def _validate_base_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported scheme: {parsed.scheme}")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("empty host in KB_REST_BASE_URL")
    if parsed.scheme == "http" and not _is_localhost(host):
        raise ValueError(
            "non-HTTPS KB_REST_BASE_URL only allowed for localhost"
        )
    if _is_private(host):
        raise ValueError(
            f"access to private network host '{host}' is denied"
        )
    return url.rstrip("/")


class DefaultRestKbClient(KnowledgeBaseClient):
    """Call external FAQ service per default REST contract."""

    def __init__(
        self,
        *,
        base_url: str,
        token: Optional[str] = None,
        timeout_ms: int = 5000,
    ) -> None:
        if requests is None:
            raise RuntimeError(
                "requests library is required for DefaultRestKbClient"
            )
        self._base = _validate_base_url(base_url)
        self._token = token
        self._timeout = max(0.5, timeout_ms / 1000.0)
        self._session = requests.Session()

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
        payload: dict = {"query": query}
        if top_k is not None:
            payload["top_k"] = int(top_k)
        if min_score is not None:
            payload["min_score"] = float(min_score)
        data = self._post("/faq/search", payload)
        items = data if isinstance(data, list) else data.get("hits", [])
        hits: List[SearchHit] = []
        for it in items or []:
            entry = it.get("entry") if isinstance(it, dict) else None
            if entry is None and isinstance(it, dict) and "question" in it:
                entry = it
                score = float(it.get("score", 0.0))
            else:
                score = float(it.get("score", 0.0)) if isinstance(it, dict) else 0.0
            if not entry:
                continue
            hits.append(
                SearchHit(
                    entry=FaqEntry.from_dict({**entry, "source": "remote_api"}),
                    score=score,
                )
            )
        return hits

    def list_all(self) -> List[FaqEntry]:
        data = self._get("/faq")
        items = data if isinstance(data, list) else data.get("items", [])
        return [FaqEntry.from_dict({**it, "source": "remote_api"}) for it in items]

    def upsert(self, entry: FaqEntry) -> FaqEntry:
        if not entry.id or not entry.question:
            raise ValueError("id and question are required")
        data = self._post("/faq", entry.to_dict())
        return FaqEntry.from_dict({**data, "source": "remote_api"})

    def delete(self, entry_id: str) -> bool:
        url = self._base + f"/faq/{entry_id}"
        resp = self._session.delete(
            url, headers=self._headers(), timeout=self._timeout
        )
        if resp.status_code == 404:
            return False
        if resp.status_code >= 400:
            raise RuntimeError(
                f"remote kb service returned HTTP {resp.status_code}"
            )
        return True

    def stats(self) -> KbStats:
        try:
            items = self.list_all()
            return KbStats(
                backend="remote_api",
                entry_count=len(items),
                data_source=self._base,
            )
        except Exception:  # noqa: BLE001
            return KbStats(backend="remote_api", entry_count=-1, data_source=self._base)

    # ------------------------------------------------------------------
    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _get(self, path: str):
        resp = self._session.get(
            self._base + path, headers=self._headers(), timeout=self._timeout
        )
        return self._handle(resp)

    def _post(self, path: str, payload: dict):
        resp = self._session.post(
            self._base + path,
            json=payload,
            headers=self._headers(),
            timeout=self._timeout,
        )
        return self._handle(resp)

    @staticmethod
    def _handle(resp):
        if resp.status_code >= 400:
            raise RuntimeError(
                f"remote kb service returned HTTP {resp.status_code}"
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise RuntimeError("remote kb service returned non-JSON") from exc
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], (dict, list)):
            return data["data"]
        return data


# ---------------------------------------------------------------------------
def from_env() -> Optional[DefaultRestKbClient]:
    base = os.getenv("KB_REST_BASE_URL")
    if not base:
        return None
    return DefaultRestKbClient(
        base_url=base,
        token=os.getenv("KB_REST_TOKEN"),
        timeout_ms=int(os.getenv("KB_REST_TIMEOUT_MS", "5000")),
    )
