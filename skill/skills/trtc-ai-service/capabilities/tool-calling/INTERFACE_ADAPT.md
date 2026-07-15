# tool-calling Interface Adaptation SOP

> Alpha/beta dual-track tool calling. This capability's source code has not been refactored to ports/adapters/core in this release (Phase 1 compromise),
> but the manifest already declares the full `business_contract.alpha_track` / `beta_track` / `arbitration` contracts.

---

## 1. Dual-Track Contract Overview

### 1.1 Alpha Track (local functions)

```yaml
alpha_track:
  registration_schema:
    name: string                # e.g.: query_order
    description: string         # Tool description for LLM consumption
    parameters: object          # JSON Schema
    handler: callable           # Sync or async Python function
```

Alpha track is suitable for: low latency, tight business coupling, tools that are inconvenient to expose as HTTP services.

### 1.2 Beta Track (remote APIs)

```yaml
beta_track:
  api_schema:
    method: GET | POST | PUT | DELETE | PATCH
    path: string
    request_schema: object
    response_schema: object
    auth: bearer | api_key | none
```

Beta track is suitable for: cross-service calls, tools that need to reuse existing API gateways.

### 1.3 Arbitration Rules

```yaml
arbitration:
  default_priority: alpha               # Alpha first
  fallback_on_failure: true             # Alpha failure auto-degrades to beta
  timeout_ms: 3000                       # Single-track call timeout
  merge_strategy: first_success         # Take first success only
```

---

## 2. Three Scenarios When User Interfaces Don't Match

### 2.1 Scenario 1: User's alpha-track function signature differs

**Symptom**: The user already has local functions (e.g. `def get_order(order_id, user_id) -> dict`),
but the skeleton expects parameters named `id` / `customer_id`.

**Solution**: Write a thin wrapper registration function — no need to modify the skeleton.

```python
# Inside user project
from capabilities.tool_calling.src.dispatcher import register_tool

def get_order(order_id, user_id):
    """User's existing function."""
    return {"order_id": order_id, "status": "shipped"}

# Adaptation layer: parameter remapping
register_tool(
    name="query_order",
    description="Query order status",
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "customer_id": {"type": "string"},
        },
        "required": ["id", "customer_id"],
    },
    handler=lambda id, customer_id: get_order(id, customer_id),  # Field remapping
)
```

### 2.2 Scenario 2: User's beta-track remote API uses a different protocol

**Symptom**: The remote business API is not OpenAI Tool Calling-style JSON-RPC,
but a user's own REST endpoint (e.g. `POST /api/v1/orders/query`).

**Solution**: Declare the full API schema when registering in `tools.yaml`.

```yaml
# capabilities/tool-calling/data/tools.yaml
tools:
  - name: query_order
    description: Query order status
    alpha: null                          # No local implementation
    beta:
      base_url: https://api.example.com  # Must be HTTPS
      method: POST
      path: /api/v1/orders/query
      headers:
        X-Api-Key: ${USER_KB_TOKEN}      # Read from environment variable
      request_template:
        body:
          order_no: "{{ id }}"           # Template render: map tool input id to order_no
          uid: "{{ customer_id }}"
      response_path: "$.data.order"      # Response field extraction (JSONPath)
```

> This release's advanced template rendering in tools.yaml is **not fully implemented**;
> for complex mapping needs, it's recommended to rewrite as an alpha-track local function + internal `requests` call.

### 2.3 Scenario 3: User wants to disable beta track (local functions only)

```bash
export TC_PRIORITY=alpha
export TC_DISABLE_BETA=1
```

The skeleton only uses alpha track; beta failures will not trigger. Vice versa (`TC_DISABLE_ALPHA=1`).

---

## 3. Arbitration Priority Override

The manifest defaults to `priority=alpha`; can be overridden via environment variables:

```bash
export TC_PRIORITY=beta              # Beta first (when alpha implementation is not yet stable)
export TC_PRIORITY=manifest_order    # Follow order of alpha/beta fields in tools.yaml
```

---

## 4. Phase 4 Plan: Full ports/adapters Refactor

The following will be introduced in the future:

```
capabilities/tool-calling/src/
├── ports/
│   ├── local_tool.py            # ABC: LocalTool
│   └── remote_tool.py           # ABC: RemoteToolClient
└── adapters/
    ├── alpha_python.py          # Alpha default implementation (current dispatcher behavior)
    ├── beta_rest.py             # Beta default implementation
    └── user_custom.py           # User integration wizard generator
```

This document will be supplemented with automated adaptation workflows at that time.

---

## 5. Security Checklist

- [ ] Beta track `base_url` must use https:// (localhost excepted)
- [ ] Reject private network access (9.* / 10.* / 172.16-31.* / 192.168.*)
- [ ] `Authorization` / `X-Api-Key` only from environment variables
- [ ] Alpha track handlers must not expose `eval` / `exec` / arbitrary command execution
- [ ] Tool result re-injection must have prompt injection protection (manifest.security.injection_protection)
