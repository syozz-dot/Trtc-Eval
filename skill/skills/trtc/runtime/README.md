# TRTC Topic Runtime Telemetry

Runtime log collection module for shared TRTC runtime verification and telemetry flows. Captures SDK events from the user's running application after integration is complete (Step 4.5).

## Architecture

```
telemetry_collector.py  (orchestrator: start/stop background log capture)
        │
        ├── Web:     telemetry-bridge.mjs (Puppeteer + Vite dev server)
        ├── iOS:     xcrun simctl launch --console
        └── Android: adb logcat -s TRTCSDK:* LiveCore:*
        │
        ▼
.trtc-telemetry/runtime.log  (raw captured logs)
```

## Usage

```bash
# Start collection (Web example)
python3 telemetry_collector.py --mode start --platform web --workspace /path/to/project

# ... user interacts with their app ...

# Stop collection
python3 telemetry_collector.py --mode stop --workspace /path/to/project
```

## Output

Logs are written to `<workspace>/.trtc-telemetry/runtime.log` (raw JSON lines from the bridge or platform log stream).

## Web Platform Setup

The web bridge requires Puppeteer:

```bash
cd skills/trtc/runtime
npm install
```

## Origin

Extracted and simplified from `trtc-eval` (internal eval system). Key differences:
- No nonce/anti-replay mechanism (not needed for user-facing telemetry)
- No scoring/penalty calculations
- No credential injection (user's app is already configured)
- No DOM probes or auto-run detection
- User-consented, opt-in collection
