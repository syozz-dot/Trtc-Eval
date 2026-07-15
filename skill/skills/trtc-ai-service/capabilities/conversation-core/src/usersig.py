"""TLS-SIG-API-v2 UserSig generator (pure Python, no third-party dependencies).

TRTC room authentication uses SDKAppID + SDKSecretKey to sign the UserId via HMAC-SHA256,
then compresses with zlib + base64url encodes to produce the UserSig. This implementation
matches the official ``TLSSigAPIv2`` behavior, enabling usage in a minimal skeleton without
additional SDKs.

Reference: https://cloud.tencent.com/document/product/647/17275
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import zlib


def _base64_encode(data: bytes) -> str:
    s = base64.b64encode(data).decode("utf-8")
    # TRTC custom base64url: + → *, / → -, = → _
    return s.replace("+", "*").replace("/", "-").replace("=", "_")


def _hmac_sha256(
    sdk_app_id: int,
    user_id: str,
    secret_key: str,
    current_ts: int,
    expire: int,
    base64_userbuf: str | None = None,
) -> str:
    raw_to_sign = (
        f"TLS.identifier:{user_id}\n"
        f"TLS.sdkappid:{sdk_app_id}\n"
        f"TLS.time:{current_ts}\n"
        f"TLS.expire:{expire}\n"
    )
    if base64_userbuf is not None:
        raw_to_sign += f"TLS.userbuf:{base64_userbuf}\n"
    digest = hmac.new(
        secret_key.encode("utf-8"),
        raw_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def gen_user_sig(
    sdk_app_id: int,
    sdk_secret_key: str,
    user_id: str,
    expire_seconds: int = 86400,
) -> str:
    """Generate a UserSig.

    Args:
        sdk_app_id: TRTC SDKAppID (integer).
        sdk_secret_key: TRTC SDKSecretKey.
        user_id: User identifier within the room; must remain stable.
        expire_seconds: Validity duration in seconds, default 24 hours.

    Returns:
        A UserSig string ready for use with the TRTC Web SDK for room entry.
    """
    if not sdk_app_id or not sdk_secret_key:
        raise ValueError("sdk_app_id and sdk_secret_key are required")
    if not user_id:
        raise ValueError("user_id is required")

    current_ts = int(time.time())
    sig = _hmac_sha256(
        sdk_app_id=sdk_app_id,
        user_id=user_id,
        secret_key=sdk_secret_key,
        current_ts=current_ts,
        expire=expire_seconds,
    )

    payload = {
        "TLS.ver": "2.0",
        "TLS.identifier": str(user_id),
        "TLS.sdkappid": int(sdk_app_id),
        "TLS.expire": int(expire_seconds),
        "TLS.time": int(current_ts),
        "TLS.sig": sig,
    }
    compressed = zlib.compress(json.dumps(payload).encode("utf-8"))
    return _base64_encode(compressed)
