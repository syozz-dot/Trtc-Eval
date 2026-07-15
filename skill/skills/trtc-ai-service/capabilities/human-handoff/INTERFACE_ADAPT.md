# human-handoff Interface Adaptation SOP

> When the user's existing ticket / agent dispatch system interface differs from this capability's default contract, follow this document for scenario-specific operations.
> Recommended: use `python scripts/contract-adapt.py human-handoff` for automated generation; this document is the manual fallback.

---

## 1. Default Contract Overview

This capability **calls** the user's ticket system interfaces (outbound):

| Contract | Method | Path | Purpose |
|---|---|---|---|
| `ticket.create`        | POST | `/tickets`                          | Create ticket |
| `ticket.status_query`  | GET  | `/tickets/{ticket_id}`              | Query ticket status |
| `ticket.cancel`        | POST | `/tickets/{ticket_id}/cancel`       | Cancel ticket |
| `ticket.status_callback` | POST | `/api/v1/handoff/callback/ticket-status` | Business callback (inbound) |

Full field definitions in `manifest.yaml` `business_contract.external_apis`.

---

## 2. Three-Layer Defense Mechanism

| Layer | Artifact Location | Applicable Scenario |
|---|---|---|
| **L1 Field Mapping** | Field name / simple type differences only | 90% of common cases |
| **L2 Adapter Subclass** | Auth, transport headers, error codes, URL template differences | Different auth mechanism / path/routing style |
| **L3 Full Custom Implementation** | Protocol-level differences (webhook / MQ / gRPC) | Non-REST protocols |

All three layers land in `capabilities/human-handoff/src/adapters/user_custom.py` and are enabled via `HH_ADAPTER=user_custom`.

---

## 3. L1 Field Mapping (Most Common)

### 3.1 Applicability

- User interface is still REST + JSON
- Only field name / field path differences (within `adapter_slots` scope)
- Field types are consistent (string ↔ string, int ↔ int)

### 3.2 Steps

**Step 1**: Paste the user's curl or OpenAPI

```bash
# User's ticket creation interface
curl -X POST https://crm.example.com/api/v2/work_orders \
  -H 'X-Auth-Token: xxx' \
  -d '{
    "customer_id": "u001",
    "title": "Refund issue",
    "level": "P2",
    "messages": ["..."]
  }'
# Response: { "id": "WO123", "rank": 5, "wait_estimate": 150 }
```

**Step 2**: Write mapping file `capabilities/human-handoff/src/adapters/user_custom_mapping.yaml`

```yaml
# Field path mapping: left = default contract field, right = user's actual field
ticket.create:
  request:
    user_id:     customer_id
    subject:     title
    priority:    level                  # Value mapping below
    transcript:  messages
  response:
    ticket_id:       id
    queue_position:  rank
    eta_seconds:     wait_estimate
  # Enum value mapping
  enum_map:
    request.priority:
      low:    P3
      normal: P2
      high:   P1
      urgent: P0

ticket.status_query:
  request:
    ticket_id: id
  response:
    ticket_id: id
    status:    state
  enum_map:
    response.status:
      pending:    queued
      processing: in_progress
      closed:     done
      canceled:   cancelled
```

**Step 3**: Generate adapter (via tool)

```bash
python scripts/contract-adapt.py human-handoff \
  --base-url https://crm.example.com \
  --auth-header "X-Auth-Token" \
  --mapping capabilities/human-handoff/src/adapters/user_custom_mapping.yaml
```

The tool generates `user_custom.py` based on the mapping, automatically inheriting `DefaultRestHandoffClient` and overriding field mapping logic.

**Step 4**: Enable

```bash
export HH_ADAPTER=user_custom
export HH_REST_BASE_URL=https://crm.example.com
export HH_REST_TOKEN=<your-token>     # Optional; leave empty if no token
```

---

## 4. L2 Adapter Subclass (Auth / Path Style Differences)

### 4.1 Applicability

- Auth method is not Bearer (e.g. `X-Auth-Token`, `HMAC-SHA256` signature, dual token)
- Different path templates (e.g. `/tickets/{id}` vs `/work-orders/by-id/{id}`)
- Error codes are not HTTP standard (e.g. returns 200 but body has `code != 0`)

### 4.2 Template Code

```python
# capabilities/human-handoff/src/adapters/user_custom.py
from typing import List, Optional

from ..core.models import Ticket, TicketStatus
from .default_rest import DefaultRestHandoffClient


class UserCustomHandoffClient(DefaultRestHandoffClient):
    """User ticket system adapter (L2)."""

    def _headers(self) -> dict:
        # Override auth method
        h = {"Content-Type": "application/json"}
        if self._token:
            h["X-Auth-Token"] = self._token        # Not Bearer
        return h

    def create_ticket(
        self,
        *,
        user_id: str,
        subject: str = "",
        description: str = "",
        priority: str = "normal",
        transcript: Optional[List[str]] = None,
    ) -> Ticket:
        # TODO Field remapping
        payload = {
            "customer_id": user_id,
            "title": subject,
            "level": {"low": "P3", "normal": "P2", "high": "P1", "urgent": "P0"}[priority],
            "messages": list(transcript or []),
        }
        data = self._post("/api/v2/work_orders", payload)
        return Ticket(
            ticket_id=str(data["id"]),
            user_id=user_id,
            subject=subject,
            description=description,
            priority=priority,
            queue_position=int(data.get("rank", 0)),
            eta_seconds=int(data.get("wait_estimate", 0)),
            transcript=list(transcript or []),
        )

    def query_status(self, ticket_id: str) -> Optional[TicketStatus]:
        # TODO Path template remapping
        data = self._get(f"/api/v2/work_orders/by-id/{ticket_id}", optional=True)
        if data is None:
            return None
        # TODO Status enum remapping
        status_map = {"queued": "pending", "in_progress": "processing", "done": "closed"}
        return TicketStatus(
            ticket_id=str(data["id"]),
            status=status_map.get(data.get("state", ""), data.get("state", "pending")),
            agent_id=data.get("operator"),
        )


def from_env() -> Optional["UserCustomHandoffClient"]:
    import os
    base = os.getenv("HH_REST_BASE_URL")
    if not base:
        return None
    return UserCustomHandoffClient(
        base_url=base,
        token=os.getenv("HH_REST_TOKEN"),
        timeout_ms=int(os.getenv("HH_REST_TIMEOUT_MS", "5000")),
    )
```

### 4.3 Enable

```bash
export HH_ADAPTER=user_custom
export HH_REST_BASE_URL=https://crm.example.com
export HH_REST_TOKEN=<your-token>
```

---

## 5. L3 Full Custom (Protocol Differences)

### 5.1 Applicability

- Business side uses webhooks (you push messages; business side async callbacks)
- Business side uses message queues (Kafka / RocketMQ / RabbitMQ)
- Business side uses gRPC / gRPC-Web
- User system is fully custom; no "generic ticket interface" concept

### 5.2 Template Code

```python
# capabilities/human-handoff/src/adapters/user_custom.py
from typing import List, Optional

from ..core.models import OverallStatus, Ticket, TicketStatus, TicketStatusEnum, now_ts
from ..ports.handoff_client import HandoffClient


class UserCustomHandoffClient(HandoffClient):
    """User custom protocol adapter (L3: directly implements HandoffClient)."""

    def __init__(self, **kwargs):
        # TODO Initialize your client: Kafka producer / gRPC channel / webhook poster etc.
        ...

    def create_ticket(self, *, user_id, subject="", description="",
                      priority="normal", transcript=None) -> Ticket:
        # TODO Send ticket creation message using your own protocol
        # e.g.: self._kafka.send("ticket.create", {...})
        ticket_id = Ticket.new_id()
        return Ticket(
            ticket_id=ticket_id,
            user_id=user_id,
            subject=subject,
            description=description,
            priority=priority,
            status=TicketStatusEnum.PENDING.value,
            transcript=list(transcript or []),
            created_at=now_ts(),
        )

    def query_status(self, ticket_id: str) -> Optional[TicketStatus]:
        # TODO Query status from your storage / API
        ...

    def cancel_ticket(self, ticket_id: str, reason: str = "") -> Optional[Ticket]:
        # TODO
        ...

    def overall_status(self) -> OverallStatus:
        return OverallStatus(
            agent_pool_size=-1, available_agents=-1, waiting=-1, connected=-1, capacity=-1
        )

    def list_tickets(self, *, limit=50, status=None) -> List[Ticket]:
        # Dashboard may use this; return empty if remote backend doesn't support enumeration
        return []


def from_env():
    return UserCustomHandoffClient(
        broker=__import__("os").getenv("HH_BROKER_URL", ""),
    )
```

---

## 6. Inbound Callback Integration (`ticket.status_callback`)

If the user's ticket system supports proactive callbacks, enabling inbound mode is recommended:

### 6.1 Our Exposed Callback Endpoint

```
POST /api/v1/handoff/callback/ticket-status
Content-Type: application/json
{
  "ticket_id": "WO123",
  "status": "processing",
  "agent_id": "alice"
}
```

Returns `{"code": 0, "message": "ok"}`.

> **Note**: This release's router.py has **not implemented** this inbound endpoint; using inbound mode requires registering a FastAPI route in user_custom.py and implementing it yourself, or wait for Phase 4 auto-generation by contract-adapt.py.

### 6.2 Inbound Field Mapping (different callback field names)

If the user system's callback uses field names like `id` / `state` / `operator`, add inbound mapping in user_custom.py:

```python
# Register the callback endpoint in the router and call this method to convert the payload
def _map_inbound(payload: dict) -> dict:
    return {
        "ticket_id": payload.get("id") or payload.get("ticket_id"),
        "status": {"queued": "pending", "in_progress": "processing"}.get(
            payload.get("state"), payload.get("status")
        ),
        "agent_id": payload.get("operator") or payload.get("agent_id"),
    }
```

---

## 7. Switch / Verify

### 7.1 Enable user_custom

```bash
export HH_ADAPTER=user_custom
# Takes effect after service restart
```

### 7.2 Unit Self-Check

```bash
python -c "
from capabilities.human_handoff.src.adapters.factory import build_default
c = build_default()
print('adapter:', type(c).__name__)
t = c.create_ticket(user_id='u_test', subject='ping')
print('created:', t.to_dict())
print('queried:', c.query_status(t.ticket_id))
"
```

### 7.3 End-to-End

```bash
curl -X POST http://localhost:3000/api/v1/handoff/request \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"u_test","reason":"I want to complain"}'
```

---

## 8. Security Checklist

- [ ] `HH_REST_BASE_URL` must use https:// (localhost excepted)
- [ ] Default reject private network addresses (9.* / 10.* / 172.16-31.* / 192.168.* / 169.254.*)
- [ ] Auth token only from environment variables — **no hardcoding** in user_custom.py
- [ ] Remote exceptions do not print response bodies (may contain PII)
- [ ] `Authorization` / `X-Auth-Token` headers auto-redacted in logs (handled by skeleton `log_redaction`)
