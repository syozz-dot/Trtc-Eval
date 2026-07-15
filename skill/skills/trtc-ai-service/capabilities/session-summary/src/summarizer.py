"""Structured summary generator.

Strategy:
- Offline heuristic (default): extract questions / to-do keywords / key nouns, done locally with zero dependencies.
- LLM secondary summarization (optional, requires LLM_API_KEY): serialize turns and call OpenAI-compatible protocol.

Output JSON:
    {
      "topics":      ["..."],
      "user_intents": ["..."],
      "next_actions": ["..."],
      "highlights":  ["..."],
      "engine":      "heuristic" | "llm",
      "model":       "gpt-4o-mini" | null
    }
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from .recorder import SessionRecord

logger = logging.getLogger(__name__)


_QUESTION_RE = re.compile(r"[^?？]+[?？]")
_ACTION_RE = re.compile(r"(I want|please help|need to|please)([^。.!?？!\n]+)", re.IGNORECASE)
_NOUN_RE = re.compile(r"[A-Z][A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}")
_STOPWORDS = {"the", "a", "an", "because", "so", "when", "can", "need"}


def _heuristic(record: SessionRecord) -> Dict[str, Any]:
    topics: List[str] = []
    intents: List[str] = []
    actions: List[str] = []
    highlights: List[str] = []
    seen_topic, seen_intent, seen_action = set(), set(), set()
    for t in record.turns:
        if t.role != "user":
            continue
        for q in _QUESTION_RE.findall(t.text):
            q = q.strip()
            if q and q not in seen_intent:
                intents.append(q[:120])
                seen_intent.add(q)
        for m in _ACTION_RE.finditer(t.text):
            phrase = (m.group(1) + m.group(2)).strip()[:120]
            if phrase and phrase not in seen_action:
                actions.append(phrase)
                seen_action.add(phrase)
        for noun in _NOUN_RE.findall(t.text):
            if noun in _STOPWORDS or len(noun) > 24:
                continue
            if noun not in seen_topic and len(topics) < 8:
                topics.append(noun)
                seen_topic.add(noun)
    if record.turns:
        highlights.append(f"{len(record.turns)} turns recorded")
    return {
        "topics": topics,
        "user_intents": intents[:5],
        "next_actions": actions[:5],
        "highlights": highlights,
        "engine": "heuristic",
        "model": None,
    }


def _llm_summarize(record: SessionRecord) -> Dict[str, Any]:
    api_key = os.getenv("LLM_API_KEY")
    api_url = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    if not api_key:
        raise RuntimeError("LLM_API_KEY not configured")
    import requests

    transcript = "\n".join(f"[{t.role}] {t.text}" for t in record.turns[-50:])
    prompt = (
        "You are a session summary assistant. Summarize the following conversation as JSON with keys: topics, user_intents,"
        " next_actions, highlights. Each value is a string array (max 5 items)."
        "Do not include any sensitive information (API Key/Token etc.).\n"
        f"Conversation content:\n{transcript}\n"
        "Output JSON only."
    )
    resp = requests.post(
        api_url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {"highlights": [content[:512]]}
    parsed.setdefault("topics", [])
    parsed.setdefault("user_intents", [])
    parsed.setdefault("next_actions", [])
    parsed.setdefault("highlights", [])
    parsed["engine"] = "llm"
    parsed["model"] = model
    return parsed


def summarize(record: SessionRecord, *, prefer_llm: bool = True) -> Dict[str, Any]:
    if prefer_llm and os.getenv("LLM_API_KEY"):
        try:
            return _llm_summarize(record)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM summarize failed, fallback to heuristic: %s", exc)
    return _heuristic(record)


def summarize_paragraph(record: SessionRecord) -> Optional[str]:
    """Generate a one-paragraph narrative summary of the session via LLM.

    Used by the handoff flow to fill a ticket's Description with an LLM summary of the
    chat from AI connect → handoff trigger. Returns None if LLM is not configured or the
    session has no turns (caller then leaves the description unchanged).
    """
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        return None
    if not record.turns:
        return None
    import requests

    api_url = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    transcript = "\n".join(f"[{t.role}] {t.text}" for t in record.turns[-50:])
    prompt = (
        "You are a customer-service ticket summarizer. Read the conversation below between "
        "a customer and an AI assistant, then write ONE concise paragraph (2-4 sentences) "
        "summarizing what the customer asked about and what was discussed, from the moment "
        "the AI connected up to the point the customer requested a human agent. Do not invent "
        "facts not present in the conversation. Do not include any sensitive data (API key / "
        "token etc.). Output only the paragraph, with no preamble.\n"
        f"Conversation:\n{transcript}\n"
    )
    resp = requests.post(
        api_url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    return (data["choices"][0]["message"]["content"] or "").strip() or None
