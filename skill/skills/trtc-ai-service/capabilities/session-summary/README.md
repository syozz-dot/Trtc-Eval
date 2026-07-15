# session-summary · Session Summary + Structured Abstract

> Auto-archives turn records for each session on top of conversation-core,
> and produces structured summaries (topics / intents / next_actions) after calling `finalize`.

## Install

```bash
python scripts/add-capability.py session-summary
```

## Configuration

| Env Variable | Default | Description |
|:---|:---|:---|
| `SS_STORAGE_DIR`    | `capabilities/session-summary/data/` | Summary landing directory (permissions 0600) |
| `SS_RETENTION_DAYS` | `30` | Retention days; auto-cleanup after expiry |
| `SS_LLM_SUMMARY`    | `true` | Whether to call LLM for secondary summarization (depends on `LLM_API_KEY`) |

## REST API

| Method | Path | Purpose |
|:---|:---|:---|
| GET  | `/api/v1/summary/_list?_offset=0&_limit=20` | Recent summary list |
| GET  | `/api/v1/summary/{session_id}` | Single session summary details |
| POST | `/api/v1/summary/{session_id}/finalize` | Close session and trigger summary |

## Summary Output

```json
{
  "topics":       ["order", "shipping"],
  "user_intents": ["When will my order ship?"],
  "next_actions": ["Please update my address"],
  "highlights":   ["12 turns recorded"],
  "engine":       "heuristic",
  "model":        null
}
```

LLM path falls back to local heuristic implementation on failure, ensuring offline availability.

## Security

- Disk file permissions enforced to `0600`
- Sensitive fields (`secret_id / api_key / token / credential`) redacted before writing
- Transcript text max length `4096`
