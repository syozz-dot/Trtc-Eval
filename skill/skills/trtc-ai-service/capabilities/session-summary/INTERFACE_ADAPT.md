# session-summary Interface Adaptation SOP

> Session summary + structured summary write-back to CRM / ticketing / data platform.
> This capability's source code has not been refactored to ports/adapters/core in this release (Phase 1 compromise).

---

## 1. Default Contract Overview

| Contract | Method | Path | Purpose |
|---|---|---|---|
| `summary.write_to_crm`  | POST | `/sessions/{session_id}/summary` | Write finalized summary to user's CRM / ticketing system |
| `summary.llm_summarize` | —   | Reuses conversation-core `llm.chat_completions` | LLM secondary summarization, no separate adaptation needed |

Full field details in `manifest.yaml.business_contract.external_apis`.

---

## 2. Default Behavior

session-summary currently **only writes to local files by default** (path `data/<session_id>.json`),
and does not actively write to any remote system. This means:

- Integrators need to scan the `data/` directory themselves or call `/api/v1/summary/{session_id}` to pull
- No outbound calls are enabled, keeping security risk low
- Suitable as a "draft state"; integrators plug into business systems on demand

---

## 3. Enabling CRM Write-Back

### 3.1 Configure Default Contract

```bash
# Enable CRM write-back + user's CRM API fully matches default contract
export SS_CRM_WRITE_ENABLED=1
export SS_CRM_BASE_URL=https://crm.example.com
export SS_CRM_TOKEN=sk-xxx
```

> The current capability source code has **not implemented** the `SS_CRM_*` environment variable logic;
> you need to write an adapter subclass per §4 below before enabling. After Phase 4's full refactor, this will become out-of-the-box.

### 3.2 Custom Field Mapping

If the user's CRM API has different field names (e.g. `summary` / `priority` / `tags`), write a simple
webhook middleware layer or append an HTTP call at the end of `recorder.py`'s `finalize_session` function.

Reference code snippet (manually append to `src/recorder.py`'s finalize section):

```python
import os, requests
def _maybe_write_crm(session_id: str, summary_payload: dict):
    base = os.getenv("SS_CRM_BASE_URL")
    if not base or os.getenv("SS_CRM_WRITE_ENABLED") != "1":
        return
    # Field remapping example
    body = {
        "session_id": session_id,
        "summary": summary_payload.get("topic"),       # User's field is called summary
        "priority": summary_payload.get("outcome"),    # User's field is called priority
        "tags": summary_payload.get("next_actions"),
    }
    requests.post(
        f"{base}/sessions/{session_id}/summary",
        json=body,
        headers={"Authorization": f"Bearer {os.getenv('SS_CRM_TOKEN', '')}"},
        timeout=5,
    )
```

---

## 4. Phase 4 Plan: Full ports/adapters Refactor

The following will be introduced in the future:

```
capabilities/session-summary/src/
├── ports/
│   └── crm_client.py          # ABC: write_summary / query_summary
└── adapters/
    ├── local_file.py          # Default implementation: local disk only (current behavior)
    ├── default_rest.py        # Calls per default CRM contract
    ├── mock.py                # Mock for demos
    └── user_custom.py         # User integration wizard generator
```

At that time, `SS_ADAPTER=user_custom` will support direct switching without manually modifying recorder.py.

---

## 5. Security Checklist

- [ ] CRM write-back auto-redacts sensitive fields (`secret_id` / `api_key` / `token` etc.)
- [ ] `SS_CRM_BASE_URL` must use https:// (localhost excepted)
- [ ] Reject private network addresses
- [ ] Disk file permissions enforced to 0600 (declared in manifest.security.storage)
- [ ] Summary transcripts filter out sensitive user PII (phone / ID numbers) — current capability **not implemented**; user's business layer must handle this
