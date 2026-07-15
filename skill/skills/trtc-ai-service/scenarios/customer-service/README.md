# scenarios/customer-service —— Path A Default Recipe

> Companion doc: repo root `SKILL.md` (Path A SOP §5).

This directory is the "ready-to-use" AI customer service demo for Path A — after the user says
"Build me an AI customer service agent with TRTC", the Coding Agent follows the 6-step workflow
in `SKILL.md §5` to install the `knowledge-base` + `human-handoff` + `session-summary` capability packages, run
`post-install-patch.py`, overlay the UI, and serve the **Voice Agent UI** at `http://localhost:3000`.

---

## Default Artifact: voice-customer-service (v1.1)

- **Real Voice Agent**: Built on conversation-core voice pipeline (TRTC enterRoom + agent/start + ASR/LLM/TTS)
- **Silent RAG**: Frontend calls `/api/v1/kb/search` on every user message; hits are **not shown as cards**, instead absorbed naturally by the LLM (keeping the conversation stream clean)
- **Handoff Queue Animation**: 8s progress bar + shimmer highlight + countdown; then calls `/handoff/connect` simulating `demo_agent_alex` pickup; polling for `state=connected` switches the badge
- **Product / Order Business Panel**: Left sidebar, clicking a card auto-initiates an inquiry
- **Design Compliant**: Light glassmorphism + purple-pink accent + Lucide SVG icons + tokens.css; **zero emoji** in UI
- **English-only**: All UI copy / mock data / FAQ / keyword triggers are in English (targeting overseas developers)
- **Top Bar LED hover tooltips**: Clear separation of Tencent Cloud (CAM/STS control plane) / TRTC (media data plane) / LLM (replaceable inference engine) responsibilities

---

## Directory Overview

```
scenarios/customer-service/
├── README.md                                 ← This file
├── recipe.yaml                               ← Path A recipe (parsed by AI)
├── system-prompt.template.md                 ← Neutral system prompt template
├── sample-data/
│   └── faq-sample.json                       ← 5 demo FAQ entries (English)
└── ui/
    ├── design-system/
    │   └── DESIGN_GUIDELINES.md              ← Design spec (mandatory)
    ├── voice-customer-service/               ← ⭐ Default UI (v1.1 Voice Agent)
    │   ├── README.md
    │   ├── index.html                        ← Contains Lucide SVG icon defs + three-column layout
    │   ├── app.js                            ← TRTC pipeline + silent KB + HH progress bar + dedup
    │   ├── styles.css                        ← Light glassmorphism + tooltip + progress animation
    │   ├── mock-shop.json                    ← 3 products + 3 orders (English)
    │   └── tokens.css                        ← Light glassmorphism design tokens (hand-aligned to the running theme)
    ├── widget-floating/                      ← Alternative: lightweight text IM floating widget (no TRTC voice)
    └── admin-board/                          ← Ticket agent dashboard (operations-side)
```

---

## For AI / Developers: Manual Deployment

> Path A SOP is driven by `SKILL.md §5`; below is the **bare command version** (for local manual verification):

```bash
# 1. Install KB + HH + session-summary (default mock + local_queue adapters)
python3 scripts/add-capability.py knowledge-base human-handoff session-summary --apply --json

# 2. Post-install patch (fix legacy injection misalignment + write default .env capability config + validate server.py)
python3 scripts/post-install-patch.py

# 3. UI overlay: voice-customer-service (default) + admin-board
cp scenarios/customer-service/ui/voice-customer-service/{index.html,app.js,styles.css,data.js,mock-shop.json,tokens.css} \
   capabilities/conversation-core/web-demo/
mkdir -p capabilities/conversation-core/web-demo/admin
cp -R scenarios/customer-service/ui/admin-board/. \
      capabilities/conversation-core/web-demo/admin/

# 4. Start (first launch creates venv + pip install, 30-60s)
bash start.sh
```

After startup, access:

| Entry | URL | Purpose |
|---|---|---|
| AI Voice Agent | http://localhost:3000 | End-user voice + text dual-mode conversation |
| Admin board | http://localhost:3000/static/admin/ | Agent view / connect / close tickets |
| Health probe | http://localhost:3000/api/v1/health | Three LED JSON |
| API docs | http://localhost:3000/docs | FastAPI Swagger |

> ⚠ Previous docs incorrectly mentioned `/admin/tickets` — that route does not exist. **Correct path is `/static/admin/`**.

---

## Switching to Another UI

If you don't want the voice channel and only need a lightweight text IM floating widget, change Step 3 to:

```bash
cp -R scenarios/customer-service/ui/widget-floating/. \
      capabilities/conversation-core/web-demo/
```

`widget-floating` calls `/api/v1/kb/search` + `/api/v1/handoff/request` (pure REST text IM) — it does **not** open a TRTC room.

---

## Design Language

- Fully references `design_tokens.json` v1.1.0; all color values / font sizes / spacing in the UI use CSS variables
- Font family locked to `SF Pro / Inter / Helvetica Neue`
- **Emoji disabled** in UI; status indicators use `color.status.{success,info,warning,error}` namespace
- Frosted glass panels include `@supports` fallback; older browsers degrade to semi-transparent solid panels

Any changes to `tokens.css` must first modify `design_tokens.json`, then recompile.

---

## Going to Production

1. **KB**: `KB_ADAPTER=mock` → `local_json` (point to real FAQ file) or `default_rest` (connect to external knowledge base)
2. **Handoff**: `HH_ADAPTER=local_queue` → `default_rest`; if the API diverges from the default contract, use the `SKILL.md §8.3` contract-adapt flow to generate `user_custom.py`
3. **UI**: The `<aside class="sidebar">` product / order panel in voice-customer-service is placeholder mock data; swap `loadShopPanel` with your own endpoint for real integration
4. **HTTPS**: `bash start.sh --https` (self-signed cert; in production, use a reverse proxy with a real certificate)
5. **Dashboard Auth**: `/static/admin/` is currently a public static page; for production, add a path prefix + reverse proxy authentication
