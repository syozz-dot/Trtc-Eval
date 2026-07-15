# tool-calling · Alpha/Beta Dual-Track Tool Calling

> Provides local function (alpha) + remote API (beta) tool calling on top of conversation-core,
> with alpha-first by default and automatic degradation to beta on alpha failure (P1 arbitration rules).

## Install

```bash
python scripts/add-capability.py tool-calling
```

## Configuration

| Env Variable | Default | Description |
|:---|:---|:---|
| `TC_REGISTRY_FILE` | `capabilities/tool-calling/data/tools.yaml` | Tool declaration file |

Tool declaration format in `data/tools.yaml`, supports hot-reload (`POST /api/v1/tools/reload`).

## REST API

| Method | Path | Purpose |
|:---|:---|:---|
| GET  | `/api/v1/tools/list`   | List all tools |
| POST | `/api/v1/tools/invoke` | Explicit invocation `{name, params, priority?}` |
| POST | `/api/v1/tools/reload` | Reload registry |

## In-Conversation Trigger

Push the following text to `agent/control` to trigger:

```
/tool get_order {"order_id": "A1234"}
```

The dispatcher replaces the original text with a `[tool_result ...]...[/tool_result]` block and injects it into the LLM.

## Arbitration Rules

- `priority=alpha` (default): alpha first, then beta
- `priority=beta`: beta first, then alpha
- `priority=manifest_order`: follow declaration order

Automatic degradation to the next available track on any track failure; returns `ok=false` and `fallback_chain` when all fail.

## Security

- Beta track enforces HTTPS (except `http://localhost*`);
- Tool name ≤ 64, trigger text ≤ 4096;
- Tool parameters auto-redacted in logs (manifest declares `log_redaction.patterns`).
