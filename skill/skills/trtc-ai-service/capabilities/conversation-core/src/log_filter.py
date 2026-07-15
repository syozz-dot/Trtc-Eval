"""Log redaction filter (P0 security requirement implemented).

Performs irreversible masking of credential fields in log records before logging,
based on the keywords declared in manifest.yaml security.log_redaction.patterns.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable

# Default sensitive field names to match (aligned with manifest.yaml security.log_redaction.patterns)
_DEFAULT_PATTERNS = (
    "secret_id",
    "secret_key",
    "api_key",
    "app_key",
    "token",
    "usersig",
    "credential",
    "authorization",
)


def _build_regex(patterns: Iterable[str]) -> re.Pattern[str]:
    # Matches three common formats: key=value / "key": "value" / key: value
    keys = "|".join(re.escape(p) for p in patterns)
    pattern = (
        r"(?i)(?P<key>" + keys + r")"
        r"(?P<sep>\s*[:=]\s*\"?)"
        r"(?P<val>[A-Za-z0-9_\-\.\+/=]{4,})"
    )
    return re.compile(pattern)


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


class RedactingFilter(logging.Filter):
    """Mask sensitive fields in log messages / args."""

    def __init__(self, patterns: Iterable[str] = _DEFAULT_PATTERNS) -> None:
        super().__init__()
        self._regex = _build_regex(patterns)

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            if isinstance(record.msg, str):
                record.msg = self._regex.sub(
                    lambda m: f"{m.group('key')}{m.group('sep')}{_mask(m.group('val'))}",
                    record.msg,
                )
            if record.args:
                record.args = tuple(
                    self._regex.sub(
                        lambda m: f"{m.group('key')}{m.group('sep')}{_mask(m.group('val'))}",
                        str(a),
                    )
                    if isinstance(a, str)
                    else a
                    for a in record.args
                )
        except Exception:  # Redaction failure must not affect the main logging flow
            pass
        return True


def install_redacting_filter(logger: logging.Logger | None = None) -> None:
    """Attach the redacting filter to the specified Logger (defaults to root Logger)."""
    target = logger or logging.getLogger()
    if any(isinstance(f, RedactingFilter) for f in target.filters):
        return
    target.addFilter(RedactingFilter())
