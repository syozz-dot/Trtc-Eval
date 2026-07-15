# Q4 —— Capability Selection (multi-select; defaults to none)

> Path B Question 4. AI uses `ask_followup_question` in **multi-select** mode (`multiSelect: true`).
>
> Answer written to internal variable `extra_capabilities` (string array), used to determine:
> 1. Capability list for Path B assembly command: `add-capability.py conversation-core <selected>`
> 2. recipe.yaml `capabilities.install` list
>
> **Important**: Unlike Path A (which defaults to KB + HH), Path B defaults to **none**, installing only the conversation-core skeleton.
> Only capabilities **explicitly selected** by the user are added to the list.

---

## What the AI should say

> Question 4: Besides the conversation skeleton (conversation-core), what additional capabilities do you want to layer on?
> (Multi-select; you can also select none. Defaults to skeleton only.)

`options`:

```text
① knowledge-base   — FAQ / knowledge base retrieval
② human-handoff    — Human handoff + ticket flow (with agent dashboard)
③ tool-calling     — Let the AI call your business tools / remote APIs
④ session-summary  — Auto-generate a summary / ticket note when a session ends
```

`multiSelect: true`

---

## Capabilities not in options (explanation talking points)

| Capability | Why it's not listed |
|---|---|
| `digital-human` | Currently a placeholder capability (manifest hasn't completed ports/adapters); for digital human, please wait for a future version |

---

## Validation / Fallback

- Q4 all empty → skip `add-capability.py` call (conversation-core skeleton only, already in the repo)
- Selected `tool-calling` but Q2 picked "voice-only call" → warn "tool calling will not display intermediate status on a voice-only channel"; ask user to confirm whether to keep it
- Selected `session-summary` but `LLM_API_KEY` not configured → warn "session summary depends on LLM Key; please complete LLM Key configuration in §7"

---

## Options → Assembly Command

```bash
# AI executes at Path B Step 6 (skip the entire command when Q4 is empty):
python3 scripts/add-capability.py \
    knowledge-base human-handoff tool-calling session-summary \
    --apply --json
```

> The actual command only includes the capability names the user **selected**; the above is the "select all" example.

---

## Answer write-back

```yaml
# Render to <workspace>/recipe.yaml
capabilities:
  required:
    - name: conversation-core
      role: skeleton
  install:
    # User-selected capabilities (append one entry per selected; adapter defaults to manifest.config.adapter.default)
    - name: knowledge-base
      adapter: mock
    - name: human-handoff
      adapter: local_queue
  optional: []
  excluded:
    - name: digital-human          # Not participating in this release
```
