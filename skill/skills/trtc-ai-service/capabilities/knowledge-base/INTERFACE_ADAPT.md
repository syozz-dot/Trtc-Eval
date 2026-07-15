# knowledge-base Interface Adaptation SOP

> When the user's existing knowledge base / FAQ / retrieval system API diverges from this capability's default contract, follow this document for scenario-specific operations.
> Recommended: use `python scripts/contract-adapt.py knowledge-base` for automated generation; this document is the manual fallback.

---

## 1. Default Contract Overview

This capability **calls** the user's knowledge base interfaces (outbound):

| Contract | Method | Path | Purpose |
|---|---|---|---|
| `faq.search`  | POST   | `/faq/search`        | Keyword search |
| `faq.list`    | GET    | `/faq`               | List all entries |
| `faq.upsert`  | POST   | `/faq`               | Create / update |
| `faq.delete`  | DELETE | `/faq/{entry_id}`    | Delete entry |

Full field definitions in `manifest.yaml` `business_contract.external_apis`.

---

## 2. Three-Layer Defense Mechanism

| Layer | Artifact Location | Applicable Scenario |
|---|---|---|
| **L1 Field Mapping** | Only field name / simple type differences | 90% of common cases |
| **L2 Adapter Subclass** | Auth / path / error code differences | User's own KB system |
| **L3 Full Custom Implementation** | Protocol-level differences (vector DB / GraphQL / gRPC) | Non-REST protocols |

All layers land in `capabilities/knowledge-base/src/adapters/user_custom.py` and are enabled via `KB_ADAPTER=user_custom`.

---

## 3. L1 Field Mapping (most common)

### 3.1 Applicability Check

- User API is still REST + JSON
- Only field name differences (within `adapter_slots` scope)

### 3.2 Steps

**Step 1**: Paste user's curl or OpenAPI

```bash
curl -X POST https://kb.example.com/api/v3/search \
  -H 'X-Api-Key: xxx' \
  -d '{
    "keyword": "refund",
    "limit": 3
  }'
# Response:
# {
#   "results": [
#     { "doc_id": "k001", "title": "How to refund", "content": "...", "tags": ["refund"], "relevance": 0.92 }
#   ]
# }
```

**Step 2**: Write mapping table `capabilities/knowledge-base/src/adapters/user_custom_mapping.yaml`

```yaml
faq.search:
  request:
    query:  keyword              # Field name mapping
    top_k:  limit
  response:
    # response is array form; transformer needs to map results[] to hits[]
    hits:   results
    "hits[].entry.id":       "results[].doc_id"
    "hits[].entry.question": "results[].title"
    "hits[].entry.answer":   "results[].content"
    "hits[].entry.keywords": "results[].tags"
    "hits[].score":          "results[].relevance"

faq.list:
  response:
    items: data                  # User uses data not items
    "items[].id":       "data[].doc_id"
    "items[].question": "data[].title"
    "items[].answer":   "data[].content"
    "items[].keywords": "data[].tags"
```

**Step 3**: Generate adapter

```bash
python scripts/contract-adapt.py knowledge-base \
  --base-url https://kb.example.com \
  --auth-header "X-Api-Key" \
  --mapping capabilities/knowledge-base/src/adapters/user_custom_mapping.yaml
```

**Step 4**: Enable

```bash
export KB_ADAPTER=user_custom
export KB_REST_BASE_URL=https://kb.example.com
export KB_REST_TOKEN=<your-api-key>
```

---

## 4. L2 Adapter Subclass (auth / path style differences)

### 4.1 Applicability Check

- Auth method is not Bearer (e.g. `X-Api-Key`, signature-based auth)
- Different path templates
- Different response wrapping (e.g. `{ code, msg, data: { ... } }`)

### 4.2 Template Code

```python
# capabilities/knowledge-base/src/adapters/user_custom.py
from typing import List, Optional

from ..core.models import FaqEntry, SearchHit
from .default_rest import DefaultRestKbClient


class UserCustomKbClient(DefaultRestKbClient):
    """User's own KB system adapter (L2)."""

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._token:
            h["X-Api-Key"] = self._token       # Not Bearer
        return h

    def search(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
    ) -> List[SearchHit]:
        if not query.strip():
            return []
        payload = {
            "keyword": query,                  # Field remapping
            "limit": int(top_k or 3),
        }
        # User API path is different
        data = self._post("/api/v3/search", payload)
        results = data.get("results", []) if isinstance(data, dict) else (data or [])
        hits: List[SearchHit] = []
        for r in results:
            hits.append(
                SearchHit(
                    entry=FaqEntry(
                        id=str(r.get("doc_id", "")),
                        question=str(r.get("title", "")),
                        answer=str(r.get("content", "")),
                        keywords=list(r.get("tags") or []),
                        source="remote_api",
                    ),
                    score=float(r.get("relevance", 0.0)),
                )
            )
        return hits

    def list_all(self) -> List[FaqEntry]:
        data = self._get("/api/v3/docs")
        items = data.get("data", []) if isinstance(data, dict) else (data or [])
        return [
            FaqEntry(
                id=str(it.get("doc_id", "")),
                question=str(it.get("title", "")),
                answer=str(it.get("content", "")),
                keywords=list(it.get("tags") or []),
                source="remote_api",
            )
            for it in items
        ]


def from_env() -> Optional["UserCustomKbClient"]:
    import os
    base = os.getenv("KB_REST_BASE_URL")
    if not base:
        return None
    return UserCustomKbClient(
        base_url=base,
        token=os.getenv("KB_REST_TOKEN"),
        timeout_ms=int(os.getenv("KB_REST_TIMEOUT_MS", "5000")),
    )
```

---

## 5. L3 Full Custom (vector DB / GraphQL / gRPC)

### 5.1 Applicability Check

- User uses vector database (Milvus / Pinecone / Qdrant) for semantic search
- User uses GraphQL instead of REST
- User uses gRPC

### 5.2 Template Code (vector DB example)

```python
# capabilities/knowledge-base/src/adapters/user_custom.py
from typing import List, Optional

from ..core.models import FaqEntry, KbStats, SearchHit
from ..ports.kb_client import KnowledgeBaseClient


class UserCustomKbClient(KnowledgeBaseClient):
    """Vector DB adapter example (L3: directly implements KnowledgeBaseClient)."""

    def __init__(self, **kwargs):
        # TODO Initialize vector DB client:
        # self._milvus = MilvusClient(uri=...)
        # self._embedder = SentenceTransformer(...)
        ...

    def search(self, query, *, top_k=None, min_score=None) -> List[SearchHit]:
        # TODO Call embedder + vector retrieval
        # vec = self._embedder.encode(query)
        # results = self._milvus.search(vec, top_k=top_k or 3)
        results = []
        return [
            SearchHit(
                entry=FaqEntry(id=r["id"], question=r["q"], answer=r["a"]),
                score=float(r["distance"]),
            )
            for r in results
        ]

    def list_all(self) -> List[FaqEntry]:
        # TODO Vector DBs may not support enumeration; return empty or raise NotSupported
        return []

    def upsert(self, entry: FaqEntry) -> FaqEntry:
        # TODO Write vectors
        return entry

    def delete(self, entry_id: str) -> bool:
        # TODO
        return False

    def stats(self) -> KbStats:
        return KbStats(backend="vector_db", entry_count=-1)


def from_env():
    import os
    return UserCustomKbClient(
        endpoint=os.getenv("KB_VECTOR_ENDPOINT", ""),
        api_key=os.getenv("KB_VECTOR_TOKEN", ""),
    )
```

---

## 6. Switch / Verify

### 6.1 Enable user_custom

```bash
export KB_ADAPTER=user_custom
# Takes effect after service restart
```

### 6.2 Unit Self-Check

```bash
python -c "
from capabilities.knowledge_base.src.adapters.factory import build_default
c = build_default()
print('adapter:', type(c).__name__)
hits = c.search('refund')
for h in hits:
    print(' ', h.score, h.entry.question)
"
```

### 6.3 End-to-End

```bash
curl -X POST http://localhost:3000/api/v1/kb/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"refund","top_k":3}'
```

---

## 7. Security Checklist

- [ ] `KB_REST_BASE_URL` must use https:// (localhost excepted)
- [ ] Default reject private network addresses
- [ ] Auth token only from environment variables
- [ ] User-uploaded FAQ content sanitized via `_strip_html` (built into router)
- [ ] Remote exceptions do not print response bodies
