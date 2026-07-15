# frontend-spa Adapter

> Connect the conversation-core skeleton REST API to any frontend SPA.
> The Agent selects the appropriate subdirectory template based on the current `tech_stack` during the L1 phase and renders it into the user's project.

| tech_stack | Template | Default Target |
|:---|:---|:---|
| react / next | `react/VoiceAgent.tsx.tpl` | `src/components/${COMPONENT_NAME}.tsx` |
| vue          | `vue/VoiceAgent.vue.tpl`   | `src/components/${COMPONENT_NAME}.vue` |
| angular      | `angular/voice-agent.component.ts.tpl` | `src/app/voice-agent/voice-agent.component.ts` |

## Dependency Installation (written by Agent into package.json)

- `trtc-sdk-v5 >= 5.0.0`

## Security

- Templates use `${SKELETON_BASE_URL}` for fetch; in production this must be replaced with an HTTPS address (skeleton manifest `security.network.enforce_https = true`).
- TRTC SDK requires a wss channel; allow in CSP:
  ```
  connect-src https://${SKELETON_BASE_URL} wss://*.trtc.tencent-cloud.com;
  ```

## Capability Overlay

- With `tool-calling` installed: type `/tool xxx {...}` in the Send box to trigger local tool calls.
- With `human-handoff` installed: sending keywords like "talk to agent" triggers the queue-and-connect flow.
