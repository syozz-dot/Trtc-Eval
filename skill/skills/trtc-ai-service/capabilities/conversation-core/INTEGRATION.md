# conversation-core · Integration Guide (Agent-readable)

> This document is for **AI coding assistants / integration agents** to automatically
> merge the conversation-core skeleton into user projects. All instructions are designed for programmatic parsing and execution.

---

## Section 1 · Tech Stack Detection

At the integration entry point, the Agent detects user project characteristics in the following order, outputting a `tech_stack` label:

| Signal File | Key Field | Inferred Tech Stack |
|:---|:---|:---|
| `package.json` | `dependencies.react` | `react` |
| `package.json` | `dependencies.vue` | `vue` |
| `package.json` | `dependencies['@angular/core']` | `angular` |
| `package.json` | `dependencies.express` / `koa` / `fastify` | `express` / `koa` / `fastify` |
| `package.json` | `dependencies.next` | `next` |
| `pom.xml` | `<artifactId>spring-boot-starter</artifactId>` | `spring-boot` |
| `build.gradle` | `org.springframework.boot` | `spring-boot` |
| `pom.xml` | `quarkus-core` | `quarkus` |
| `requirements.txt` / `pyproject.toml` | `flask` / `fastapi` / `django` | `flask` / `fastapi` / `django` |

If multiple tech stack candidates are detected, the most specific one takes priority:
`next > react/vue/angular > express/koa/fastify > spring-boot/quarkus > flask/fastapi/django`.

---

## Section 2 · Adapter Rule Matching

Read the `integration.auto_adapters` list from this capability's `manifest.yaml`; the first entry whose `tech_stack` matches becomes the target adapter:

```text
match(tech_stack_detected, manifest.integration.auto_adapters[*].tech_stack)
  → adapter_name (e.g. "frontend-spa")
```

The mapping from adapter name to actual generator is provided by Phase 2; this skeleton only declares the interface contract.

---

## Section 3 · Code Generation and Merging

Phase 1 skeleton only exposes REST APIs (default port `3000`). How integrators call the skeleton from their own projects:

### 3.1 Frontend (any SPA)

```js
// 1) Health check (top status bar)
const health = await fetch('http://localhost:3000/api/v1/health').then(r => r.json());

// 2) Request room credentials
const cfg = await fetch('http://localhost:3000/api/v1/get_config', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
}).then(r => r.json());
const { session_id, sdk_app_id, room_id, user_id, user_sig } = cfg.data;

// 3) Join room via TRTC Web SDK using sdk_app_id / user_sig (encapsulated by frontend capability package)

// 4) Start AI channel bot
await fetch('http://localhost:3000/api/v1/agent/start', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ session_id, language: 'zh' })
});
```

### 3.2 Backend (any runtime)

| Runtime | Injection Point | Generator Output |
|:---|:---|:---|
| Express / Koa / Fastify | Router layer | Middleware code (reverse proxy `/api/v1/*` to skeleton process) |
| Spring Boot / Quarkus | Filter Chain | Filter code + `@Value("${trtc.voice-agent.endpoint}")` injection |
| Flask / FastAPI / Django | Route handler | Decorators + sub-router mounting |

### 3.3 Injection Points (declarative)

`manifest.yaml.injection_points` declares 5 standard injection points. Phase 2 capability packages reference them by `id`, e.g.:

```yaml
# knowledge-base capability manifest.yaml snippet
extensions:
  - inject_at: "agent.before_start"
    code_template: "templates/inject_kb_to_instructions.py.tpl"
```

---

## Section 4 · Three-Level Degradation Path

| Level | Trigger Condition | Agent Behavior |
|:---:|:---|:---|
| **L1 Full Auto-Merge** | Tech stack detected successfully and code generation has no conflicts | Write directly into user project and auto-run `npm install` / `pip install` |
| **L2 Semi-Auto Guide** | Tech stack detected successfully but code generation fails (syntax / path conflicts) | Output `INTEGRATION_GUIDE.md` with template code + manual injection steps |
| **L3 Manual API Fallback** | Tech stack cannot be identified | Output REST API docs (base path `/api/v1`) + SDK package install commands |

L2 / L3 output templates are located in `integration-templates/` (provided by Phase 2).

---

## Section 5 · Verification Checks

After integration, the Agent must execute these checks in order:

1. **Process alive** — `curl -s http://localhost:3000/api/v1/health | jq .status`, expected `"ok"`.
2. **Three LEDs** — `health.checks.{tencent_cloud,trtc,llm}.status == "ok"`.
3. **Session handshake** — `POST /api/v1/get_config` → returns non-empty `session_id` and `user_sig`.
4. **Text injection** — After starting AI, call `POST /api/v1/agent/control { text: "ping" }` expecting `delivered: true`.
5. **Graceful stop** — `POST /api/v1/agent/stop` returns `status: "stopped"`.

On any step failure, the Agent must output a diagnostic JSON:

```json
{ "step": "get_config", "error": "...", "remediation": "Check that TRTC_SDK_APP_ID in .env is an integer" }
```

---

## Appendix A · Error Code Dictionary

| Error Code | Meaning | Remediation |
|:---|:---|:---|
| E001 | Tencent Cloud SecretId/SecretKey invalid | Re-run `python scripts/setup-credentials.py` |
| E002 | TRTC SDKAppID/SDKSecretKey invalid or UserSig generation failed | Verify SDKAppID is an integer; SecretKey is complete |
| E003 | LLM API Key invalid | Check that `LLM_API_URL` is an OpenAI-compatible endpoint |
| E004 | Network unreachable | Check egress IP whitelist / proxy |
| E005 | Service not activated | Enable Conversational AI in TRTC Console |

## Appendix B · Security Compliance

- Credentials only from environment variables (`security.credential_storage.source = env-only`)
- Credential cache and `.env` file enforced to permission `0600`
- End-to-end HTTPS (`security.network.enforce_https = true`)
- Log redaction filter installed at process startup (see `src/log_filter.py`)
- XSS / Prompt Injection protection switches declared in `security.injection_protection`
