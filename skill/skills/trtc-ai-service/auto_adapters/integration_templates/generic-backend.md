# Generic Backend Integration Guide (L2 Semi-Auto)

> When the Agent has identified your backend tech stack but auto-rendering failed, follow these steps to complete the integration.
> Core idea: mount a reverse proxy route in your web framework that transparently forwards `${ROUTE_PREFIX}/*`
> to the skeleton process's `${API_PREFIX}/*`.

## 1. Deploy conversation-core Skeleton

```bash
cd capabilities/conversation-core
python -m src.server     # Default listens on 0.0.0.0:3000
```

## 2. Copy Reverse Proxy Template

| Framework | Template |
|:---|:---|
| Express   | `auto_adapters/node-backend/express.js.tpl` |
| Koa       | `auto_adapters/node-backend/koa.js.tpl` |
| Fastify   | `auto_adapters/node-backend/fastify.js.tpl` |
| Spring Boot | `auto_adapters/java-backend/springboot/VoiceAgentFilter.java.tpl` |
| Quarkus   | `auto_adapters/java-backend/quarkus/VoiceAgentFilter.java.tpl` |
| Flask     | `auto_adapters/python-backend/flask.py.tpl` |
| FastAPI   | `auto_adapters/python-backend/fastapi.py.tpl` |
| Django    | `auto_adapters/python-backend/django.py.tpl` |

Replace placeholder variables (`${SKELETON_BASE_URL}` / `${API_PREFIX}` / `${ROUTE_PREFIX}`).

## 3. Register Route

Mount the router / filter / blueprint in your app entry point as described in the template's `install_hint`.

## 4. Security Checklist

- **HTTPS**: Enforce in production.
- **SSRF**: The skeleton address must not come directly from user input; if connecting to an internal network skeleton, first confirm with the user explicitly.
- **Request Body Limit**: Default `64KB`, preventing large payloads from overwhelming the ASR/LLM pipeline.
- **Auth**: Inject auth logic (JWT / API Key) in the reverse proxy; the skeleton itself only trusts requests from the reverse proxy source.

## 5. Verify

```bash
curl -s http://localhost:8000${ROUTE_PREFIX}/health | jq .status
# Expected: "ok"
```
