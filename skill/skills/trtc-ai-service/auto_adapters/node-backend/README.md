# node-backend Adapter

Connect the conversation-core skeleton as a reverse proxy into a Node.js backend,
keeping the skeleton address hidden from the frontend and allowing the backend to inject auth / rate limiting / business policies before and after forwarding.

| Framework | Template | Default Install Location |
|:---|:---|:---|
| Express | `express.js.tpl` | `routes/voice-agent.js` |
| Koa     | `koa.js.tpl`     | `routes/voice-agent.js` |
| Fastify | `fastify.js.tpl` | `routes/voice-agent.js` |

## Configuration

| Env Variable | Default | Description |
|:---|:---|:---|
| `SKELETON_BASE_URL` | `http://localhost:3000` | Skeleton process address |
| `API_PREFIX`        | `/api/v1`             | Skeleton REST prefix |
| `ROUTE_PREFIX`      | `/voice-agent`         | Self-mounting path |

## Security

- **SSRF Protection**: The template detects whether `SKELETON_BASE_URL` falls within private network ranges (`10/192.168/172.16-31/9/11/21/30/127`),
  and will output a warning in production; internal network access requires explicit user confirmation.
- **HTTPS**: Enforced in production deployment.
- **Request Body Limit**: Default `64KB`, preventing malicious large payloads from overwhelming the skeleton ASR/LLM pipeline.
