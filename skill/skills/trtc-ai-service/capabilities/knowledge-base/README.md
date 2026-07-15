# knowledge-base · FAQ Retrieval Capability

> Adds minimal FAQ retrieval to the conversation-core skeleton with zero external dependencies.

## Install

```bash
# From repo root
python scripts/add-capability.py knowledge-base
```

## Configuration

| Env Variable | Default | Description |
|:---|:---|:---|
| `KB_DATA_FILE` | `capabilities/knowledge-base/data/faq.json` | FAQ data file |
| `KB_TOP_K`    | `3`   | Max entries to backfill per query |
| `KB_MIN_SCORE`| `0.1` | Hit threshold (entries below this are not injected) |

## REST API

| Method | Path | Purpose |
|:---|:---|:---|
| GET  | `/api/v1/kb/list`    | List all entries |
| POST | `/api/v1/kb/search`  | Keyword search |
| POST | `/api/v1/kb/upsert`  | Create / update |
| DELETE | `/api/v1/kb/{id}`  | Delete |
| POST | `/api/v1/kb/reload`  | Hot-reload from file |

## Injection Strategy

- `agent.before_start`: Append matched FAQ entries to the end of LLM `instructions`.
- `server.router_extension`: Mount `/api/v1/kb/*` sub-router.

## Data Format

```json
[
  {
    "id": "faq_xxx",
    "question": "What ...?",
    "answer": "...",
    "keywords": ["alias1", "alias2"]
  }
]
```

## Security

- HTML tags are automatically stripped when writing entries (XSS defense).
- Length limits: `question ≤ 1024`, `answer ≤ 4096`, `query ≤ 256`.
