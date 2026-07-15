"""DefaultRestHandoffClient — call external ticketing system per business_contract default contract.

Corresponding contracts:
- POST   /tickets               ticket.create
- GET    /tickets/{ticket_id}   ticket.status_query
- POST   /tickets/{ticket_id}/cancel    ticket.cancel

Environment variables:
- HH_REST_BASE_URL    Ticketing system base URL (required; must not point to private network, see §Security)
- HH_REST_TOKEN       Bearer Token (optional)
- HH_REST_TIMEOUT_MS  Timeout (default 5000)

Security constraints (aligned with project security_rules):
- Only allow https:// or http://localhost / 127.0.0.1
- Default reject common private network ranges (9.* / 10.* / 11.* / 21.* / 30.* / 169.254.* / 172.16-31.* / 192.168.*)
- Log redaction auto-masks Authorization

Dependency: only requests (already in conversation-core/requirements.txt), no new deps.
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

from ..core.models import (
    OverallStatus,
    Ticket,
    TicketStatus,
    TicketStatusEnum,
    now_ts,
)
from ..ports.handoff_client import HandoffClient


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Security: private network and loopback check
# ---------------------------------------------------------------------------
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
        raise ValueError("empty host in HH_REST_BASE_URL")
    # Non-HTTPS only allowed for localhost
    if parsed.scheme == "http" and not _is_localhost(host):
        raise ValueError(
            "non-HTTPS HH_REST_BASE_URL only allowed for localhost"
        )
    # Reject private network ranges (prevent SSRF)
    if _is_private(host):
        raise ValueError(
            f"access to private network host '{host}' is denied; "
            "set HH_REST_ALLOW_PRIVATE=1 to override (not recommended)"
        )
    return url.rstrip("/")


# ---------------------------------------------------------------------------
# Client implementation
# ---------------------------------------------------------------------------
class DefaultRestHandoffClient(HandoffClient):
    """Call external ticketing system per default REST contract."""

    def __init__(
        self,
        *,
        base_url: str,
        token: Optional[str] = None,
        timeout_ms: int = 5000,
    ) -> None:
        if requests is None:
            raise RuntimeError(
                "requests library is required for DefaultRestHandoffClient"
            )
        self._base = _validate_base_url(base_url)
        self._token = token
        self._timeout = max(0.5, timeout_ms / 1000.0)
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # HandoffClient required implementations
    # ------------------------------------------------------------------
    def create_ticket(
        self,
        *,
        user_id: str,
        subject: str = "",
        description: str = "",
        priority: str = "normal",
        transcript: Optional[List[str]] = None,
    ) -> Ticket:
        payload = {
            "user_id": user_id,
            "subject": subject,
            "description": description,
            "priority": priority or "normal",
            "transcript": list(transcript or []),
        }
        data = self._post("/tickets", payload)
        ticket_id = str(data.get("ticket_id") or "").strip()
        if not ticket_id:
            raise RuntimeError("remote ticket service did not return ticket_id")
        return Ticket(
            ticket_id=ticket_id,
            user_id=user_id,
            subject=subject,
            description=description,
            priority=priority or "normal",
            status=TicketStatusEnum.PENDING.value,
            queue_position=int(data.get("queue_position") or 0),
            eta_seconds=int(data.get("eta_seconds") or 0),
            transcript=list(transcript or []),
            reason=description[:128] if description else "",
            created_at=now_ts(),
            updated_at=now_ts(),
        )

    def query_status(self, ticket_id: str) -> Optional[TicketStatus]:
        data = self._get(f"/tickets/{ticket_id}", optional=True)
        if data is None:
            return None
        return TicketStatus(
            ticket_id=str(data.get("ticket_id") or ticket_id),
            status=str(data.get("status") or TicketStatusEnum.PENDING.value),
            agent_id=data.get("agent_id"),
            updated_at=float(data.get("updated_at") or 0.0) or None,
        )

    def cancel_ticket(self, ticket_id: str, reason: str = "") -> Optional[Ticket]:
        data = self._post(
            f"/tickets/{ticket_id}/cancel",
            {"ticket_id": ticket_id, "reason": reason},
            optional=True,
        )
        if data is None:
            return None
        return Ticket(
            ticket_id=ticket_id,
            user_id="",  # remote may not return user_id
            status=TicketStatusEnum.CANCELED.value,
            reason=reason,
            updated_at=now_ts(),
            closed_at=now_ts(),
        )

    def overall_status(self) -> OverallStatus:
        # Remote backend does not expose overall status; return placeholder (for /api/v1/handoff/status compatibility)
        return OverallStatus(
            agent_pool_size=-1,
            available_agents=-1,
            waiting=-1,
            connected=-1,
            capacity=-1,
        )

    # ------------------------------------------------------------------
    # Internal：HTTP
    # ------------------------------------------------------------------
    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _get(self, path: str, *, optional: bool = False):
        url = self._base + path
        resp = self._session.get(url, headers=self._headers(), timeout=self._timeout)
        return self._handle(resp, optional=optional)

    def _post(self, path: str, payload: dict, *, optional: bool = False):
        url = self._base + path
        resp = self._session.post(
            url,
            json=payload,
            headers=self._headers(),
            timeout=self._timeout,
        )
        return self._handle(resp, optional=optional)

    @staticmethod
    def _handle(resp, *, optional: bool):
        if resp.status_code == 404 and optional:
            return None
        if resp.status_code >= 400:
            # Do not print response body (may contain sensitive info)
            raise RuntimeError(
                f"remote ticket service returned HTTP {resp.status_code}"
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise RuntimeError("remote ticket service returned non-JSON") from exc
        # Response may be {"data": {...}} or flat {...}
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
            return data["data"]
        return data


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def from_env() -> Optional[DefaultRestHandoffClient]:
    base = os.getenv("HH_REST_BASE_URL")
    if not base:
        return None
    return DefaultRestHandoffClient(
        base_url=base,
        token=os.getenv("HH_REST_TOKEN"),
        timeout_ms=int(os.getenv("HH_REST_TIMEOUT_MS", "5000")),
    )
