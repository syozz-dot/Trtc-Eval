# `business_contract` Field Specification (v1.0)

> Scope: the `business_contract` section in `capabilities/<name>/manifest.yaml`.
>
> Purpose: enable capability packages to **structurally** declare the business interface contracts they call / are called by,
> so that `scripts/contract-adapt.py` (Phase 3 Stage 4) can generate executable adapters based on them,
> and the assembly guide (Path A / Path B) can proactively list the contract manifest at the end.

---

## 1. Top-Level Structure

```yaml
business_contract:
  port_class: "<dotted.path>"             # Full dotted path to ABC abstract base class
  default_adapter: "<dotted.path>"        # Default implementation (production)
  mock_adapter: "<dotted.path>"           # Mock implementation (demo / video recording)
  external_apis:                          # outbound / inbound interface contract list
    - <ExternalApi>
  customization_sop: "INTERFACE_ADAPT.md" # Path to interface adaptation SOP (relative to capability root)
```

**Special case**: `tool-calling` does not use the port/adapter abstraction; it uses the alpha/beta dual-track contract section defined in §5 instead.

---

## 2. `external_apis[]` Field Definition

```yaml
- name: <string>                  # Contract name (snake_case dot-delimited), globally unique
  direction: outbound | inbound   # outbound = we call the business side; inbound = business side calls back to us
  method: GET | POST | PUT | DELETE | PATCH
  path: <string>                  # Path template, may contain {placeholder}
  description: <string>           # One-line description (for assembly wrap-up printing)
  request_schema:                 # Request schema (simplified JSON Schema)
    <field>: <type | enum[...] | object | array>
  response_schema:                # Response schema
    <field>: <type | enum[...] | object | array>
  adapter_slots:                  # Field paths allowed for user remapping (dot-delimited)
    - <request|response>.<field-path>
  auth:                           # (optional) Auth method
    type: bearer | api_key | none
    location: header | query
    name: <header-name | query-key>
  retry:                          # (optional) Retry policy
    max: <int>
    backoff_ms: <int>
  timeout_ms: <int>               # (optional) Timeout
```

### 2.1 `type` Value Convention

| Type | Meaning |
|---|---|
| `string` | String |
| `int` / `integer` | Integer |
| `float` / `number` | Float |
| `bool` / `boolean` | Boolean |
| `string[]` / `int[]` / `<T>[]` | Homogeneous array |
| `enum[a, b, c]` | Enum literal |
| `object` | Nested object (can be further expanded as sub-schema) |
| Nested dict | Write nested structure directly |

### 2.2 `adapter_slots` Field Path Rules

- Starts with `request.` or `response.`
- Nested levels use dot separation: `response.data.ticket_id`
- Arrays use `[]`: `request.transcript[]`
- Only lists fields **allowed for user remapping**; unlisted fields are treated as "our contract is fixed, user modification forbidden"

### 2.3 Special Nature of `direction = inbound`

An inbound contract means "the business side calls back to us", in which case:
- `path` is the endpoint we expose (e.g.: `/api/v1/handoff/callback/ticket-status`)
- `request_schema` is the payload structure sent by the business side
- `response_schema` is the ack structure we return (typically `{code: int, message: string}`)
- `adapter_slots` declares "business side field names may differ from our expectations", used by contract-adapt to generate inbound field mappers

---

## 3. Naming Conventions

| Element | Rule | Example |
|---|---|---|
| `name` | `<domain>.<action>` snake_case | `ticket.create`, `faq.search`, `crm.write` |
| `port_class` | `src.ports.<file>.<ClassName>` | `src.ports.handoff_client.HandoffClient` |
| `default_adapter` / `mock_adapter` | `src.adapters.<file>.<ClassName>` | `src.adapters.local_queue.LocalQueueHandoffClient` |

---

## 4. Full Example: `human-handoff`

```yaml
business_contract:
  port_class: "src.ports.handoff_client.HandoffClient"
  default_adapter: "src.adapters.local_queue.LocalQueueHandoffClient"
  mock_adapter: "src.adapters.mock.MockHandoffClient"
  customization_sop: "INTERFACE_ADAPT.md"
  external_apis:
    - name: ticket.create
      direction: outbound
      method: POST
      path: /tickets
      description: "Create a new ticket in the ticketing system when user triggers handoff"
      request_schema:
        user_id: string
        subject: string
        description: string
        priority: enum[low, normal, high, urgent]
        transcript: string[]
      response_schema:
        ticket_id: string
        queue_position: int
        eta_seconds: int
      adapter_slots:
        - request.subject
        - request.priority
        - response.ticket_id
        - response.queue_position
        - response.eta_seconds
      auth:
        type: bearer
        location: header
        name: Authorization
      timeout_ms: 5000

    - name: ticket.status_query
      direction: outbound
      method: GET
      path: /tickets/{ticket_id}
      description: "Poll ticket status for queue progress updates"
      request_schema:
        ticket_id: string
      response_schema:
        ticket_id: string
        status: enum[pending, processing, closed, canceled]
        agent_id: string
        updated_at: int
      adapter_slots:
        - response.status
        - response.agent_id
      timeout_ms: 3000

    - name: ticket.cancel
      direction: outbound
      method: POST
      path: /tickets/{ticket_id}/cancel
      description: "Notify ticketing system when user cancels handoff"
      request_schema:
        ticket_id: string
        reason: string
      response_schema:
        ticket_id: string
        canceled: bool
      adapter_slots:
        - request.reason
      timeout_ms: 3000

    - name: ticket.status_callback
      direction: inbound
      method: POST
      path: /api/v1/handoff/callback/ticket-status
      description: "Callback from ticketing system to notify status changes (optional; when disabled, status_query polling is used instead)"
      request_schema:
        ticket_id: string
        status: enum[pending, processing, closed, canceled]
        agent_id: string
      response_schema:
        code: int
        message: string
      adapter_slots:
        - request.status
        - request.agent_id
```

---

## 5. `tool-calling` Exclusive Contract Section (replaces §1 port/adapter triple)

```yaml
business_contract:
  alpha_track:                          # Alpha track: local function registration spec
    interface: "src.ports.local_tool.LocalTool"
    registration_schema:
      name: string                     # Tool name (globally unique)
      description: string
      parameters: object               # JSON Schema describing parameter structure
      handler: callable                # Function object (runtime-only)
    invocation_schema:
      input: object                    # Same schema as parameters
      output: object                   # User-defined return structure
    fail_fast: bool                    # Default true: local exceptions thrown immediately for arbitration decisions

  beta_track:                           # Beta track: remote business API integration spec
    interface: "src.ports.remote_tool.RemoteToolClient"
    api_schema:
      method: enum[GET, POST, PUT, DELETE, PATCH]
      path: string
      request_schema: object
      response_schema: object
      auth: enum[bearer, api_key, none]
    timeout_ms: 5000
    retry: { max: 1, backoff_ms: 200 }

  arbitration:                          # Arbitration rules
    default_priority: enum[alpha, beta, manifest_order]
    fallback_on_failure: bool
    timeout_ms: int                     # Single-track call timeout; triggers fallback on expiry
    merge_strategy: enum[first_success, alpha_then_beta_diff]
```

`merge_strategy` values:

| Value | Behavior |
|---|---|
| `first_success` | Return immediately on priority track success; backup track not called (default) |
| `alpha_then_beta_diff` | Both tracks called; diff log recorded when results differ (for canary comparison) |

---

## 6. How `contract-adapt.py` Consumes This Field

1. Read `business_contract.external_apis[].request_schema` / `response_schema`
2. Parse user-submitted curl / OpenAPI, extract the user API's schema
3. Compare against `adapter_slots` list to generate field mapping `mapping.yaml`
4. Render adapter template (inheriting `port_class`), output to `src/adapters/user_custom.py`
5. Three-level degradation:
   - **L1**: Only `adapter_slots` field differences → fully executable adapter
   - **L2**: Schema nesting or type differences exist → adapter template + TODO comments
   - **L3**: Protocol-level differences (webhook / MQ / gRPC) or parse failure → output corresponding `INTERFACE_ADAPT.md` section path

---

## 7. Validation Rules (mandatory at resolver stage)

| Rule | Error Code | Behavior |
|---|---|---|
| `port_class` / `default_adapter` / `mock_adapter` any not importable | `BC001` | Resolve failure, block install |
| `external_apis[].name` duplicate | `BC002` | Same as above |
| `direction = outbound` without `method` or `path` | `BC003` | Same as above |
| `adapter_slots` path not found in `request_schema` / `response_schema` | `BC004` | Warning only, does not block |
| `tool-calling.arbitration.default_priority` invalid value | `BC005` | Resolve failure |
| `auth.type = bearer` but no env variable source declared | `BC006` | Warning only |

Implementation location: `scripts/lib/contract_resolver.py` (Phase 3 Stage 4 implementation).
In Phase 1, only the field definitions are agreed upon; resolver validation will be implemented in Stage 4.

---

## 8. Relationship with Existing Manifest Fields

- `business_contract` and existing `extensions` / `endpoints` / `integration` fields **do not affect each other**; can be independently added/removed
- `endpoints` describes "the REST endpoints we expose to the frontend / user"
- `business_contract.external_apis` describes "the interfaces we call / are called back by the business side"
- Both coexist without conflict, serving different consumers (frontend / Agent / business side)

---

## 9. Version Compatibility

- Current spec version: `v1.0`
- No forward compatibility; if a future breaking change is needed, it will be marked with a `business_contract.spec_version: "2.0"` field
- The resource resolver (`manifest_resolver.py`) currently ignores unknown fields; adding this field will not break existing Phase 1/2 functionality
