# digital-human · Digital Human Capability (Placeholder)

> Phase 2 only declares the interface contract. Rendering / lip-sync / expression driving
> and other rendering layer implementations are deferred to future iterations (Phase 3+).

## Current Capabilities

- Register placeholder REST endpoints via manifest: `/api/v1/digital-human/*`
- Does not modify skeleton runtime behavior; only serves as an integration anchor for the future rendering layer

## REST Placeholders

| Method | Path | Behavior |
|:---|:---|:---|
| GET  | `/api/v1/digital-human/status` | Returns current status / roadmap |
| POST | `/api/v1/digital-human/render` | Always returns `501 Not Implemented` |

## Roadmap

1. Integrate third-party rendering SDKs (Avatar / Lipsync / Expression)
2. Push rendering driver data via WebRTC datachannel
3. Align frame output with conversation-core TTS

## Configuration

| Env Variable | Default | Description |
|:---|:---|:---|
| `DH_ENABLED` | `false` | Keep false before real enablement to avoid accidental use |
| `DH_AVATAR_ID` | _(empty)_ | Avatar ID |
| `DH_LIPSYNC_PROVIDER` | `tencent-cloud-vmp` | Lip-sync provider |
| `DH_EXPRESSION_PROVIDER` | `internal-rule` | Expression driver provider |
