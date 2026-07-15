# conversation-core Interface Adaptation SOP

> Skeleton-layer interface adaptation guide. In this release, conversation-core has **not been refactored to ports/adapters/core** (Phase 1 compromise, deferred to Phase 4),
> so this document only explains "which interfaces can be replaced and how", without providing automated generation entry points.

---

## 1. Default Contract Overview

| Contract | Method | Path | Adaptable? |
|---|---|---|---|
| `llm.chat_completions`        | POST | `/v1/chat/completions` (OpenAI-compatible)        | **Adaptable** |
| `trtc.start_ai_conversation`  | POST | Tencent Cloud TencentCloudAPI                     | **Not adaptable** (tightly bound to Tencent Cloud) |

Full field definitions in `manifest.yaml.business_contract.external_apis`.

---

## 2. LLM Interface Replacement (most common)

The skeleton calls LLM using the OpenAI Chat Completions protocol by default:
- Default `LLM_API_URL = https://api.openai.com/v1/chat/completions`
- Supports any OpenAI-compatible proxy (DeepSeek / Qwen / Tencent Hunyuan OpenAPI / vLLM etc.)

### 2.1 OpenAI-Compatible Protocol (recommended path)

Only need to switch environment variables — **no code changes required**:

```bash
# Switch to DeepSeek
export LLM_API_URL=https://api.deepseek.com/v1/chat/completions
export LLM_API_KEY=sk-xxx
export LLM_MODEL=deepseek-chat

# Switch to Qwen (DashScope OpenAI-compatible endpoint)
export LLM_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
export LLM_API_KEY=sk-xxx
export LLM_MODEL=qwen-turbo

# Switch to self-hosted vLLM
export LLM_API_URL=http://your-vllm:8000/v1/chat/completions
export LLM_API_KEY=any-string
export LLM_MODEL=Qwen2.5-7B-Instruct
```

> Security: Self-hosted LLM must use https://; http only allowed for localhost. See `security_rules`.

### 2.2 Non-OpenAI Protocols (e.g. Claude Anthropic Messages API)

Requires introducing an "LLM protocol adapter" at the skeleton layer. This mechanism is not delivered in this release; temporary workaround:

1. Deploy an OpenAI ↔ Anthropic protocol translation gateway (e.g. LiteLLM) in the user project
2. Point the skeleton's `LLM_API_URL` to the gateway
3. The gateway handles protocol translation

```bash
# Launch LiteLLM gateway (see https://docs.litellm.ai/)
litellm --model anthropic/claude-3-5-sonnet --port 4000

# Skeleton configuration
export LLM_API_URL=http://localhost:4000/v1/chat/completions
export LLM_API_KEY=sk-anthropic-xxx
export LLM_MODEL=anthropic/claude-3-5-sonnet
```

### 2.3 Phase 4 Plan: LLM Adapter Abstraction

The skeleton will introduce a `LlmClient` abstraction (same pattern as human-handoff / knowledge-base):

```
capabilities/conversation-core/src/
├── ports/
│   └── llm_client.py          # ABC: chat / stream_chat / count_tokens
└── adapters/
    ├── openai_compat.py       # Current default implementation
    ├── claude_anthropic.py    # Native Anthropic Messages API
    ├── tencent_hunyuan.py     # Tencent Hunyuan native OpenAPI
    └── user_custom.py         # User integration wizard generator
```

This document will be supplemented with automated adaptation workflows at that time.

---

## 3. TRTC Conversational AI Control Plane (Not Adaptable)

`trtc.start_ai_conversation` / `StopAIConversation` / `ControlAIConversation` /
`ServerPushText` and other control plane interfaces are **tightly bound to the Tencent Cloud protocol**. If the user's business does not use TRTC,
they should not continue using this capability package; suggest switching to a text-only conversation approach (using conversation-core's
`text_input` / `text_output` channels, bypassing the TRTC control plane).

---

## 4. ASR / TTS Service Replacement

The skeleton uses TRTC's built-in ASR/TTS by default (declared via `STTConfig` / `TTSConfig` in StartAIConversation
requests). To switch to your own ASR/TTS, replace the provider name in the manifest's
`config.io_modality.voice_input.provider` / `voice_output.provider` fields and implement
a custom provider extension in the user project per the TRTC ConversationAI documentation.

Custom provider scaffolding is not provided in this release.

---

## 5. Security Checklist

- [ ] All 3 keys come from environment variables only — **no hardcoding**
- [ ] `LLM_API_URL` must use https:// or http://localhost
- [ ] Reject private network addresses for self-hosted LLM (except localhost)
- [ ] `LLM_API_KEY` / `Authorization` headers auto-redacted in logs (handled by skeleton `log_redaction`)
- [ ] Credential cache file permissions enforced to 600
