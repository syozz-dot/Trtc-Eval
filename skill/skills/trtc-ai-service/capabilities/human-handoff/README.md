# human-handoff · Handoff + Queue Status Sync

> Provides semantic-triggered human handoff + queue status sync + agent connection capabilities on top of conversation-core.

## Install

```bash
python scripts/add-capability.py human-handoff
```

## Configuration

| Env Variable | Default | Description |
|:---|:---|:---|
| `HH_TRIGGERS`        | See below | Strong trigger keywords, CSV |
| `HH_INTENT_KEYWORDS` | See below | Weak intent keywords, CSV |
| `HH_QUEUE_CAPACITY`  | 50   | Queue capacity |
| `HH_AGENT_POOL_SIZE` | 1    | Available agent count |
| `HH_WAIT_PER_SLOT`   | 30   | Estimated wait seconds per slot |

Default strong triggers: `talk to agent / real person / human support`
Default weak triggers: `complain / manager / supervisor / not working` (negative context excluded)

## REST API

| Method | Path | Purpose |
|:---|:---|:---|
| GET  | `/api/v1/handoff/status`         | Overall queue status |
| GET  | `/api/v1/handoff/{session_id}`   | Single session status |
| POST | `/api/v1/handoff/request`        | Explicit handoff request |
| POST | `/api/v1/handoff/connect`        | Simulate agent connection |
| POST | `/api/v1/handoff/cancel`         | Cancel request |

## State Machine

```
   idle ──request──▶ waiting ──connect──▶ connected
                       │  ▲                  │
                       │  │                  ▼
                     cancel/timeout       cancel
```

Integrators should subscribe to `/handoff/status` or `/handoff/{id}` in their agent system for sync push.

