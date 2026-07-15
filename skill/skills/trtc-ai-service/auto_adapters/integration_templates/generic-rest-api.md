# Generic REST API Integration Guide (L3 Manual Fallback)

> When the Agent cannot identify your tech stack, or it's not in the supported adapter list,
> connect directly via the REST API exposed by conversation-core.

## 1. Start the Skeleton

```bash
cd capabilities/conversation-core
python -m src.server   # Default 0.0.0.0:3000
```

## 2. Endpoint List

| Method | Path | Description |
|:---|:---|:---|
| GET  | `/api/v1/health`         | Real-time connectivity check for 3 keys |
| POST | `/api/v1/get_config`     | Issue RoomId / UserSig |
| POST | `/api/v1/agent/start`    | Start AI channel bot |
| POST | `/api/v1/agent/stop`     | Stop AI channel bot |
| POST | `/api/v1/agent/control`  | Text injection / interrupt |
| GET  | `/api/v1/sessions`       | In-memory session list (debugging) |

Capability extension endpoints:

| Capability | Prefix |
|:---|:---|
| knowledge-base   | `/api/v1/kb/*` |
| tool-calling     | `/api/v1/tools/*` |
| human-handoff    | `/api/v1/handoff/*` |
| session-summary  | `/api/v1/summary/*` |
| digital-human    | `/api/v1/digital-human/*` |

## 3. Call Examples

### 3.1 Request Room Credentials

```bash
curl -X POST http://localhost:3000/api/v1/get_config \
  -H "Content-Type: application/json" \
  -d '{}'
```

Response:

```json
{
  "code": 0,
  "data": {
    "session_id": "xxx",
    "sdk_app_id": 1234567890,
    "room_id": "987654321",
    "user_id": "u_abc",
    "user_sig": "...",
    "agent_user_id": "ai_xyz",
    "io_modality": { "voice_input": { ... } }
  }
}
```

### 3.2 Start AI Bot

```bash
curl -X POST http://localhost:3000/api/v1/agent/start \
  -H "Content-Type: application/json" \
  -d '{"session_id":"xxx","language":"zh"}'
```

### 3.3 Text Injection

```bash
curl -X POST http://localhost:3000/api/v1/agent/control \
  -H "Content-Type: application/json" \
  -d '{"session_id":"xxx","text":"Hello","interrupt":true}'
```

## 4. SDK Packages

If you'd rather not call REST directly, use these SDKs:

| Ecosystem | Package |
|:---|:---|
| npm   | `@trtc/voice-agent-sdk` |
| maven | `com.tencent.trtc:voice-agent-sdk` |
| pypi  | `trtc-voice-agent` |

> SDK versions align with skeleton manifest; in Phase 2, REST is authoritative.

## 5. Security Compliance

- **HTTPS**: Enforce in production.
- **SecretKey not sent to client**: The skeleton only sends `user_sig` (with TTL) to the client; never exposes `SDKSecretKey`.
- **Log redaction**: The skeleton includes a built-in `RedactingFilter`; the reverse proxy layer should also suppress Authorization header logging.
