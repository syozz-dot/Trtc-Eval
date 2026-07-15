# voice-customer-service — Path A Default UI (v1.1)

> Design spec: `scenarios/customer-service/ui/design-system/DESIGN_GUIDELINES.md`
> Deployment location: `capabilities/conversation-core/web-demo/` (copied by Path A SOP §6 Step 3)

---

## What This UI Solves

- conversation-core's built-in `web-demo/` is a **developer self-check page** ("Voice Agent Demo / All three indicators must be green before starting") — not suitable as a customer service artifact
- `widget-floating/` is a **lightweight text IM demo** that doesn't bring up the TRTC voice channel — only shows KB + ticket REST API
- This directory is the **real Voice Agent customer service** — based on the conversation-core voice pipeline + customer service capability overlay + business panel

---

## Feature List

| Module | Implementation |
|---|---|
| **Top Bar** | Business title + three LEDs (Cloud/TRTC/LLM) + Recheck button + session status badge; LED hover shows tooltip explaining each one's role |
| **Sidebar** | Product list (click → "I'd like to know more about..." auto-send) + order list (click → "Can you check the status of order ...") |
| **Message Flow** | IM bubbles (user right / AI left / system centered); AI subtitles real-time incremental / cumulative adaptive aggregation; user voice ASR finalize drops into bubble |
| **Voice** | One-click Start → enterRoom + agent/start; mic toggle; smart interrupt before switching |
| **Text** | sendCustomMessage(cmdId:2, type:20000) directly to AI bot; IME (Chinese input) enter-key compatible |
| **KB Silent** | Each user utterance calls `/api/v1/kb/search`; hits are **not shown as cards**, only console.debug; keeps the chat window clean |
| **Handoff** | Button + keyword trigger ("talk to agent", etc.); ticket card + 8s progress bar + shimmer highlight + countdown; on completion calls `/handoff/connect` to simulate agent connection; polls `state=connected` |
| **Dedup** | sendText active render + 30s TTL local-echo list → skips same-text subtitles replayed by the AI bot (prevents double bubbles) |

---

## File List

| File | Description |
|---|---|
| `index.html` | Three-column layout + top bar + control bar; includes Lucide-style SVG icon defs (no emoji) |
| `app.js` | Full frontend logic (health / TRTC / KB / HH / products & orders / dedup) |
| `styles.css` | Light glassmorphism theme + progress animations + tooltips; 100% via tokens.css variables |
| `mock-shop.json` | 3 products + 3 orders (English mock data) |
| `tokens.css` | Light glassmorphism design tokens (hand-aligned to the running theme; single source of truth for `--color-*`) |

---

## API Contract (Frontend Call Checklist)

```
GET  /api/v1/health                 Three-LED self-check
POST /api/v1/get_config             Get sessionId / sdkAppId / roomId / userSig / agentUserId
POST /api/v1/agent/start            { session_id, language: "en" }
POST /api/v1/agent/stop             { session_id }
POST /api/v1/kb/search              { query, top_k: 1 } (silent; no cards rendered)
POST /api/v1/handoff/request        { session_id, reason }
POST /api/v1/handoff/connect        { session_id, agent_id: "demo_agent_alex" } (for simulated connection)
POST /api/v1/handoff/cancel         { session_id }
GET  /api/v1/handoff/{session_id}   Ticket status polling; returns legacy_dict (field is `state`, not `status`)
GET  /static/mock-shop.json         Product / order data
```

> ⚠ **Legacy Field Trap**: `/handoff/*` uses `to_legacy_dict` — the field is `state`, values: `waiting / connected / closed / canceled / timeout` ("canceled" with single L), and there is **no top-level `ticket_id`** (use `session_id` as the tracking ID). `/admin/tickets` uses `to_dict`, which has both `status` + `ticket_id`.

---

## Customization Points

- **Change KB integration**: Currently `silentKbLookup` only console.debugs on hit. For real RAG, inject hit entries as system prompt context (requires backend — conversation-core doesn't support system prompt injection yet; can indirectly use `agent_runtime.system_prompt.variables`)
- **Change queue wait time**: `HANDOFF_QUEUE_MS = 8_000`
- **Change simulated agent name**: `SIM_AGENT_ID = "demo_agent_alex"`
- **Add business panels**: `renderProducts` / `renderOrders` are already templates — copy and adjust fields
- **Multi-language**: Defaults to English (`agent/start` body `language: "en"`); for Chinese/English switching, write language toggle to `state` + UI dropdown
