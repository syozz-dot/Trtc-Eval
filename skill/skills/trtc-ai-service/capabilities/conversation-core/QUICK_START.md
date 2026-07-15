# conversation-core · Quick Start

> Configure → Run → Verify, done in three steps.

## 0. Prerequisites

- Python ≥ 3.9
- Activated: Tencent Cloud account + TRTC Conversational AI application + any OpenAI-compatible LLM service

## 1. Install

```bash
# From repo root
pip install -r capabilities/conversation-core/requirements.txt
```

## 2. Configure the 3 Keys

```bash
python scripts/setup-credentials.py
```

The script interactively guides you through `[1/3] Tencent Cloud → [2/3] TRTC → [3/3] LLM` in order,
running a self-check immediately after each key is entered. On failure, it won't proceed to the next key;
if interrupted mid-way, re-running it will auto-skip keys that already passed (checkpoint resume).

Output artifacts on success:

| Path | Contents | Permissions |
|:---|:---|:---:|
| `.env` | Environment variable declarations for the 3 keys | 600 |
| `.credentials_cache` | SHA256 hashes of verified keys | 600 |
| `config-report.json` | Verification timestamp / latency / status for each key | 644 |

## 3. Launch Web Demo

```bash
bash start.sh
# Equivalent to:
# cd capabilities/conversation-core && python -m src.server
```

Open <http://localhost:3000> in your browser.

## 4. Acceptance Criteria

- [x] ASR/LLM/TTS pipeline has no hard-coded business logic (protocol passthrough only)
- [x] `setup-credentials.py` supports real-time connectivity self-check and checkpoint resume
- [x] Web Demo top status bar: all three indicator LEDs green
- [x] manifest.yaml includes skeleton type / injection points / modality / security declarations
- [x] INTEGRATION.md provides Agent-readable detection logic and three-level degradation path
- [x] `.credentials_cache` / `.env` permissions 600; no plain-text keys in logs

## 5. Next Steps

Overlay business capability packages at the 5 injection points declared in `manifest.yaml.injection_points`:

```bash
voice-agent add knowledge-base
voice-agent add tool-calling
voice-agent add human-handoff
```
