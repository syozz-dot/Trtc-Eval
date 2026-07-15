# auto_adapters - Tech Stack Decoupling Adapter Component Library

> Read by the Agent during the integration phase. Based on the tech stack identified by `stack_detector`,
> selects the corresponding adapter, renders template code, and injects it into the user's project.

## Adapter Index

| Adapter | Matching Tech Stack | Injected Artifact | Default Target |
|:---|:---|:---|:---|
| `frontend-spa` | `react` / `vue` / `angular` / `next` | `VoiceAgent.{tsx,vue,ts}` component | `src/components/` |
| `node-backend` | `express` / `koa` / `fastify` | Reverse proxy middleware | `routes/voice-agent.js` |
| `java-backend` | `spring-boot` / `quarkus` | `Filter` or `Quarkus Filter` | `src/main/java/.../VoiceAgentFilter.java` |
| `python-backend` | `flask` / `fastapi` / `django` | Decorator / sub-router | `voice_agent_proxy.py` |

## Template Rendering Variables

All `.tpl` files use `${VAR}` placeholders (to avoid conflicts with JS / Python `{{}}`):

| Variable | Default | Description |
|:---|:---|:---|
| `${SKELETON_BASE_URL}` | `http://localhost:3000` | conversation-core process address |
| `${API_PREFIX}` | `/api/v1` | Skeleton REST prefix |
| `${COMPONENT_NAME}` | `VoiceAgent` | Frontend component name |
| `${ROUTE_PREFIX}` | `/voice-agent` | Backend proxy route prefix |

## Three-Level Degradation Chain

```
L1 Full Auto:  stack_detector.primary matched → adapter.render() → write to user project
       │
       │  Failed (syntax conflict / path conflict)
       ▼
L2 Semi-Auto:  Output INTEGRATION_GUIDE.md (based on integration_templates/generic-*.md)
       │
       │  stack_detector.primary is None
       ▼
L3 Manual API: Output integration_templates/generic-rest-api.md
```

See `scripts/lib/degrader.py` and `scripts/add-capability.py` for details.
