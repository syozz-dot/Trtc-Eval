"""Handoff intent detection: keyword strong matching + weak intent (with negative context recognition).

Migrated from original trigger.py. This module does **not depend** on any adapter or global state; pure functions.
"""
from __future__ import annotations

import os
import re
from typing import List


_DEFAULT_TRIGGERS = [
    "agent", "help", "support",
    "real person", "talk to agent", "speak to a human", "human agent",
]
_DEFAULT_INTENT = ["complain", "manager", "unsatisfied", "escalate"]


def _csv_env(key: str, default: List[str]) -> List[str]:
    raw = os.getenv(key)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class IntentDetector:
    """Determine whether input text expresses a "handoff" intent using regex."""

    def __init__(
        self,
        *,
        triggers: List[str] | None = None,
        intent_keywords: List[str] | None = None,
    ) -> None:
        self._triggers = triggers if triggers is not None else _csv_env(
            "HH_TRIGGERS", _DEFAULT_TRIGGERS
        )
        self._intent = intent_keywords if intent_keywords is not None else _csv_env(
            "HH_INTENT_KEYWORDS", _DEFAULT_INTENT
        )
        self._triggers_re = re.compile(
            "|".join(re.escape(k) for k in self._triggers), re.IGNORECASE
        )
        self._intent_re = re.compile(
            "|".join(re.escape(k) for k in self._intent), re.IGNORECASE
        )
        self._negative_re = re.compile(
            r"\b(not|don't|do not|no|never)\b", re.IGNORECASE
        )

    def is_handoff_intent(self, text: str) -> bool:
        if not text or len(text) > 4096:
            return False
        if self._triggers_re.search(text):
            return True
        if self._intent_re.search(text) and not self._negative_re.search(text):
            return True
        return False


# ---------------------------------------------------------------------------
# Default singleton (keeps behavior consistent with old trigger.py; tests can manually construct new instances to override)
# ---------------------------------------------------------------------------
_default_detector: IntentDetector | None = None


def get_default_detector() -> IntentDetector:
    global _default_detector
    if _default_detector is None:
        _default_detector = IntentDetector()
    return _default_detector


def is_handoff_intent(text: str) -> bool:
    return get_default_detector().is_handoff_intent(text)
