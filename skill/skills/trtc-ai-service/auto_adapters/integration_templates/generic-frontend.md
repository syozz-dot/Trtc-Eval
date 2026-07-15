# Generic Frontend Integration Guide (L2 Semi-Auto)

> When the Agent has identified your frontend tech stack but auto-rendering failed due to path conflicts or syntax errors,
> follow these steps to complete the integration manually.

## Step 1 · Install Dependencies

```bash
npm install trtc-sdk-v5
```

## Step 2 · Copy Component Template

Choose the corresponding template from `auto_adapters/frontend-spa/` based on your framework:

- React / Next:  `react/VoiceAgent.tsx.tpl`
- Vue:           `vue/VoiceAgent.vue.tpl`
- Angular:       `angular/voice-agent.component.ts.tpl`

Copy the template content to your project's components directory and replace these placeholder variables with real values:

| Placeholder | Default | Description |
|:---|:---|:---|
| `${SKELETON_BASE_URL}` | `http://localhost:3000` | Skeleton process address |
| `${API_PREFIX}` | `/api/v1` | Skeleton REST prefix |
| `${COMPONENT_NAME}` | `VoiceAgent` | Component / file name |

## Step 3 · Mount in Parent Component

```tsx
import { VoiceAgent } from './components/VoiceAgent';

export default function Page() {
  return <main><VoiceAgent /></main>;
}
```

## Step 4 · CSP & HTTPS

If CSP is deployed in production, append:

```
connect-src https://${SKELETON_BASE_URL} wss://*.trtc.tencent-cloud.com;
```

## Step 5 · Verify

Open the page; you should see three LEDs at the top: `tencent_cloud / trtc / llm`.
Once all are green, click `Start` to join the room and talk to the AI.

If any LED is red, check `.env` and the 3 keys based on the diagnostic JSON output in the page console.
