# Q2 —— I/O Modality (4 choose 1)

> Path B Question 2. AI uses `ask_followup_question` in **single-select** mode.
>
> Answer written to internal variable `io_modality` (mapped to English enums in the table below), later used to:
> 1. Determine whether `agent_runtime.greeting` uses TTS audio
> 2. Set conversation-core `io_modality.*.enabled` fields
> 3. Decide whether the floating widget UI exposes a microphone button

---

## What the AI should say (recommend copy-pasting directly into ask_followup_question)

> Question 2: What I/O modality should be used between end users and the AI agent?

`options` (keep order; order corresponds one-to-one with enums below):

```text
① Text-only IM (user types → AI replies in text; no voice)
② Text + TTS (user types → AI replies in text + reads aloud, recommended)
③ Omni-modal (voice + text, bidirectional; user can also speak)
④ Voice-only call (user dials → AI answers → full voice; no demo UI in this release)
```

`multiSelect: false`

---

## Option → Backend Config Mapping

| User Option | Internal Enum (`io_modality`) | conversation-core io_modality Config | UI Impact |
|---|---|---|---|
| ① Text-only | `text_only` | voice_input=disabled, voice_output=disabled | Widget shows input box only; mic hidden |
| ② Text + TTS (recommended) | `text_with_tts` | voice_input=disabled, voice_output=enabled (trtc-tts) | Widget shows input box + "read aloud" toggle; mic hidden |
| ③ Omni-modal | `omni` | voice_input=enabled (trtc-asr), voice_output=enabled | Widget shows input box + mic (push-to-talk) |
| ④ Voice-only call | `voice_only` | voice_input=enabled, voice_output=enabled, text_input=disabled | No UI; backend phone gateway only (no floating widget in this release) |

---

## Validation / Fallback

- User picks ④ but Q3 picks "floating" → warn about conflict, guide user to change Q3 to "headless"
- User picks ② / ③ but LLM verification fails → save the choice, still write to recipe per user's intent; after launch, the widget will show "voice output depends on TTS key, currently unavailable"

---

## Answer write-back

```yaml
# Render to <workspace>/recipe.yaml
runtime_modality:
  preset: text_with_tts          # From "Internal Enum" column above
  voice_input: false
  voice_output: true
  text_input: true
  text_output: true
```
