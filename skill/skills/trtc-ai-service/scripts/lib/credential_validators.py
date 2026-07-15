"""Three-key validation function module (Phase 3 Stage 5).

Design purpose:
- Share the same validation functions between ``scripts/setup-credentials.py``
  (developer interactive fallback) and ``scripts/verify-credentials.py``
  (AI-driven credential-less validation).
- The validation logic itself comes from ``capabilities/conversation-core/src/health.py``;
  this module only handles "credential loading + result normalization to JSON."

Core API:
- ``validate_tencent(env)`` / ``validate_trtc(env, deep=True)`` / ``validate_llm(env)``
  → All return a ``ValidationResult`` dataclass that can be serialized via ``to_dict()``
    to ``{ok, type, error, message, latency_ms}``.

Security constraints (must follow):
- The entire process **only reads credentials from .env / process env**, never accepts keys via CLI arguments.
- Output JSON **does not contain** credential plaintext; the error field only holds error codes / brief messages.
- The caller (CLI / AI) should treat stdout as parseable JSON and not echo keys in the terminal.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# 1) Load conversation-core credential / health check modules
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
_CORE_DIR = _ROOT / "capabilities" / "conversation-core"

if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

# Lazy imports: for verify-credentials.py to call after .env is loaded
def _imports():
    from src.credentials import (  # type: ignore  # noqa: WPS433
        LlmCredential,
        TencentCloudCredential,
        TrtcCredential,
        load_from_env,
    )
    from src.health import (  # type: ignore  # noqa: WPS433
        check_llm,
        check_tencent_cloud,
        check_trtc,
    )

    return {
        "LlmCredential": LlmCredential,
        "TencentCloudCredential": TencentCloudCredential,
        "TrtcCredential": TrtcCredential,
        "load_from_env": load_from_env,
        "check_llm": check_llm,
        "check_tencent_cloud": check_tencent_cloud,
        "check_trtc": check_trtc,
    }


# ---------------------------------------------------------------------------
# 2) Error codes → AI response hints (aligned with SKILL.md §5.5 lookup table)
# ---------------------------------------------------------------------------
_ERROR_HINTS: Dict[str, str] = {
    "E001": "Tencent Cloud SecretId/SecretKey verification failed (AuthFailure / STS not enabled on account).",
    "E002": "TRTC app credentials verification failed (SDKAppID does not belong to this account / SDKSecretKey mismatch).",
    "E003": "LLM verification failed (auth 401/403 or non-200 response).",
    "E004": "Network unreachable / timeout (check proxy / firewall).",
    "E000": "Credential not configured or empty.",
}


# ---------------------------------------------------------------------------
# 3) Unified return structures
# ---------------------------------------------------------------------------
@dataclass
class ValidationResult:
    """Validation result for a single key, serialized as verify-credentials.py stdout JSON."""

    ok: bool
    type: str  # "tencent" | "trtc" | "llm" | "all"
    error: str = ""           # Error code (E000~E004 or empty)
    message: str = ""         # Human-readable description (no key plaintext)
    latency_ms: int = 0

    def to_dict(self) -> Dict:
        return {
            "ok": self.ok,
            "type": self.type,
            "error": self.error,
            "message": self.message,
            "latency_ms": self.latency_ms,
        }


@dataclass
class BatchResult:
    """Aggregate validation result (used when type=all)."""

    ok: bool
    items: List[ValidationResult] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "ok": self.ok,
            "type": "all",
            "items": [r.to_dict() for r in self.items],
        }


# ---------------------------------------------------------------------------
# 4) .env loading (independent of dotenv, avoids extra dependencies)
# ---------------------------------------------------------------------------
def load_dotenv(env_path: Optional[Path] = None) -> Dict[str, str]:
    """Read ``.env`` into ``os.environ``; returns newly added/overwritten key-value pairs.

    Path priority: parameter > capabilities/conversation-core/.env > repo root .env.
    Does not raise; returns empty dict if no file found.
    """
    candidates: List[Path] = []
    if env_path is not None:
        candidates.append(Path(env_path))
    candidates.append(_CORE_DIR / ".env")
    candidates.append(_ROOT / ".env")

    seen: Dict[str, str] = {}
    for c in candidates:
        if not c.exists() or not c.is_file():
            continue
        try:
            text = c.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in seen:
                seen[k] = v
                # 不覆盖已存在的进程级环境变量（CI / 容器优先）
                os.environ.setdefault(k, v)
        # 找到第一个就够；不再往下找以避免覆盖
        if seen:
            break
    return seen


# ---------------------------------------------------------------------------
# 5) Single-key validation functions
# ---------------------------------------------------------------------------
def validate_tencent() -> ValidationResult:
    """Validate Tencent Cloud API SecretId/SecretKey."""
    mods = _imports()
    creds = mods["load_from_env"]()
    tc = creds.tencent_cloud
    if not tc.configured:
        return ValidationResult(
            ok=False,
            type="tencent",
            error="E000",
            message="TENCENT_CLOUD_SECRET_ID / TENCENT_CLOUD_SECRET_KEY not configured",
        )
    r = mods["check_tencent_cloud"](tc)
    return ValidationResult(
        ok=r.ok,
        type="tencent",
        error="" if r.ok else (r.error_code or "E001"),
        message=r.detail if not r.ok else f"sts/GetFederationToken ok (region={tc.region})",
        latency_ms=r.latency_ms,
    )


def validate_trtc(deep: bool = True) -> ValidationResult:
    """Validate TRTC SDKAppId / SDKSecretKey.

    When deep=True and Tencent Cloud API credentials are configured, calls
    ``DescribeTRTCRealTimeQualityData`` for ownership verification;
    otherwise only does local UserSig self-consistency check.
    """
    mods = _imports()
    creds = mods["load_from_env"]()
    trtc = creds.trtc
    tc = creds.tencent_cloud if deep else None
    if not trtc.configured:
        return ValidationResult(
            ok=False,
            type="trtc",
            error="E000",
            message="TRTC_SDK_APP_ID / TRTC_SDK_SECRET_KEY not configured",
        )
    r = mods["check_trtc"](trtc, tencent=tc if (tc and tc.configured) else None)
    return ValidationResult(
        ok=r.ok,
        type="trtc",
        error="" if r.ok else (r.error_code or "E002"),
        message=r.detail or ("usersig/openapi ok" if r.ok else "trtc check failed"),
        latency_ms=r.latency_ms,
    )


def validate_llm() -> ValidationResult:
    """Validate LLM API Key (OpenAI-compatible protocol)."""
    mods = _imports()
    creds = mods["load_from_env"]()
    llm = creds.llm
    if not llm.configured:
        return ValidationResult(
            ok=False,
            type="llm",
            error="E000",
            message="LLM_API_KEY / LLM_API_URL / LLM_MODEL not configured",
        )
    r = mods["check_llm"](llm)
    return ValidationResult(
        ok=r.ok,
        type="llm",
        error="" if r.ok else (r.error_code or "E003"),
        message=r.detail or (f"chat/completions 200 ok (model={llm.model})" if r.ok else "llm failed"),
        latency_ms=r.latency_ms,
    )


def validate_all() -> BatchResult:
    """Validate all three keys sequentially; any failure → ok=False."""
    items = [validate_tencent(), validate_trtc(deep=True), validate_llm()]
    return BatchResult(ok=all(i.ok for i in items), items=items)


# ---------------------------------------------------------------------------
# 6) Error code → hint (for CLI non-JSON mode; AI does not read this)
# ---------------------------------------------------------------------------
def hint(error_code: str) -> str:
    return _ERROR_HINTS.get(error_code, "")


# ---------------------------------------------------------------------------
# 7) Self-test: allows `python -m scripts.lib.credential_validators` to run independently
# ---------------------------------------------------------------------------
def _self_test() -> int:
    load_dotenv()
    out = validate_all()
    print(json.dumps(out.to_dict(), ensure_ascii=False, indent=2))
    return 0 if out.ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_self_test())
