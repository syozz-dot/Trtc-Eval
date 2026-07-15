# Web Demo · 3-Step Quick Start Guide

> This directory is the minimal runnable verification page for conversation-core, **containing no business logic**.

## Three Steps to Start

```bash
# 1. Install dependencies (first time)
pip install -r capabilities/conversation-core/requirements.txt

# 2. Configure three keys (interactive guide)
python scripts/setup-credentials.py

# 3. Launch the Demo
bash start.sh
# or: cd capabilities/conversation-core && python -m src.server
```

Open your browser and visit <http://localhost:3000>.

## Verification Checklist

After opening the page, check in the following order:

1. The three indicator LEDs in the top status bar go from `gray` → `yellow (pending)` → `green`.
2. Once all three LEDs are green, the "Start Conversation" button becomes clickable.
3. Clicking it automatically calls `/api/v1/get_config` and `/api/v1/agent/start`; the console will output `task_id`.
4. Send any text in the text input box; you can see the ServerPushText injection record in the TRTC console.

## Troubleshooting

Click "Recheck" in the top-right corner to force a connectivity refresh. On failure, the browser console will output structured diagnostics, e.g.:

```json
{
  "tencent_cloud": { "status": "ok", "latency_ms": 120 },
  "trtc":          { "status": "ok", "latency_ms": 12 },
  "llm":           { "status": "failed", "error_code": "E003", "detail": "unauthorized: 401" }
}
```

Cross-reference the `error_code` with the `INTEGRATION.md` troubleshooting dictionary to locate the issue.

## Not in Scope for This Demo

- Real audio capture and TRTC RTC room entry (handled by Phase 2 `frontend-spa` adapter or the integrator)
- Business knowledge base / FAQ / tool calling (overlaid by standalone capability packages)
- Digital human rendering, handoff, session summaries, etc. (overlaid by standalone capability packages)
