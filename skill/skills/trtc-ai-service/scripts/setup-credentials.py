#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3-Key interactive configuration script.

Features:
  1. Each key is validated for connectivity immediately after input; failure prevents proceeding to the next key.
  2. Successfully verified keys are written to .credentials_cache (permissions 600);
     re-running the script auto-skips already-passed keys, supporting checkpoint resume (idempotent).
  3. Final artifacts: root-level `.env` file (permissions 600) + config-report.json.

Usage:
    python scripts/setup-credentials.py
    python scripts/setup-credentials.py --reset    # Clear cache and reconfigure
    python scripts/setup-credentials.py validate-tencent-cloud --secret-id ... --secret-key ...
    python scripts/setup-credentials.py validate-trtc --app-id ... --app-key ...
    python scripts/setup-credentials.py validate-llm --api-key ... --endpoint ...
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict

# Add capabilities/conversation-core to sys.path to reuse skeleton self-check logic
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
_CORE_DIR = _PROJECT_ROOT / "capabilities" / "conversation-core"
sys.path.insert(0, str(_CORE_DIR))

from src.credentials import (  # noqa: E402  pylint: disable=wrong-import-position
    LlmCredential,
    TencentCloudCredential,
    TrtcCredential,
)
from src.health import (  # noqa: E402  pylint: disable=wrong-import-position
    check_llm,
    check_tencent_cloud,
    check_trtc,
)

# Credential files go into the conversation-core directory, matching src/server.py's load_dotenv path
# (server.py: _BASE_DIR = capabilities/conversation-core, reads _BASE_DIR/.env)
CACHE_FILE = _CORE_DIR / ".credentials_cache"
ENV_FILE = _CORE_DIR / ".env"
REPORT_FILE = _PROJECT_ROOT / "config-report.json"


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
def _is_zh() -> bool:
    return os.getenv("LANG", "").lower().startswith("zh")


_T = {
    "header": ("=== TRTC Voice Agent 配置引导 ===", "=== TRTC Voice Agent Setup ==="),
    "step_tc": ("[1/3] 腾讯云 API 密钥", "[1/3] Tencent Cloud API Credentials"),
    "step_trtc": ("[2/3] TRTC 应用凭据", "[2/3] TRTC Application Credentials"),
    "step_llm": ("[3/3] 外部 LLM 接入密钥", "[3/3] External LLM API Key"),
    "input_secret_id": ("SecretId: ", "SecretId: "),
    "input_secret_key": ("SecretKey (隐藏输入): ", "SecretKey (hidden): "),
    "input_region": ("Region [ap-guangzhou]: ", "Region [ap-guangzhou]: "),
    "input_app_id": ("SDKAppID (整数): ", "SDKAppID (integer): "),
    "input_app_key": ("SDKSecretKey (隐藏输入): ", "SDKSecretKey (hidden): "),
    "input_llm_key": ("LLM API Key: ", "LLM API Key: "),
    "input_llm_url": (
        "LLM API URL [https://api.openai.com/v1/chat/completions]: ",
        "LLM API URL [https://api.openai.com/v1/chat/completions]: ",
    ),
    "input_llm_model": ("LLM Model [gpt-4o-mini]: ", "LLM Model [gpt-4o-mini]: "),
    "skip_cached": ("✓ 检测到已通过验证的缓存，跳过本步骤。", "✓ Cached credential found, skipping."),
    "validating": ("  正在校验...", "  Validating..."),
    "ok": ("✅ 校验通过", "✅ OK"),
    "fail": ("❌ 校验失败", "❌ Failed"),
    "retry": ("是否重新输入？[Y/n] ", "Retry? [Y/n] "),
    "done": ("=== 三把 Key 配置完成 ===", "=== All 3 keys configured ==="),
    "next_step": (
        "执行 `bash start.sh` 或 `python -m src.server` 启动 Web Demo。",
        "Run `bash start.sh` or `python -m src.server` to launch the Web Demo.",
    ),
}


def t(key: str) -> str:
    pair = _T[key]
    return pair[0] if _is_zh() else pair[1]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_cache() -> Dict[str, str]:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: Dict[str, str]) -> None:
    CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    try:
        os.chmod(CACHE_FILE, 0o600)
    except OSError:
        pass


def _persist_env(values: Dict[str, str]) -> None:
    """Write / merge .env file and enforce permissions 600."""
    existing: Dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()
    existing.update(values)
    rendered = "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n"
    ENV_FILE.write_text(rendered, encoding="utf-8")
    try:
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass


def _read_env_value(key: str) -> str:
    """Read a single variable value from the generated .env file (for sharing across multi-step config)."""
    if not ENV_FILE.exists():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip()
    return ""


# ---------------------------------------------------------------------------
# Interactive flow
# ---------------------------------------------------------------------------
def _step_tencent_cloud(cache: Dict[str, str], report: Dict[str, dict]) -> None:
    print()
    print(t("step_tc"))
    while True:
        secret_id = input(t("input_secret_id")).strip()
        secret_key = getpass.getpass(t("input_secret_key")).strip()
        region = input(t("input_region")).strip() or "ap-guangzhou"
        if not secret_id or not secret_key:
            print(t("fail") + ": empty input")
            continue
        sig = _hash(secret_id + ":" + secret_key)
        if cache.get("tencent_cloud") == sig:
            print(t("skip_cached"))
            return
        print(t("validating"))
        result = check_tencent_cloud(
            TencentCloudCredential(secret_id=secret_id, secret_key=secret_key, region=region)
        )
        report["tencent_cloud"] = result.to_dict() | {"checked_at": int(time.time())}
        if result.ok:
            print(f"{t('ok')} (latency {result.latency_ms}ms)")
            _persist_env(
                {
                    "TENCENT_CLOUD_SECRET_ID": secret_id,
                    "TENCENT_CLOUD_SECRET_KEY": secret_key,
                    "TENCENT_CLOUD_REGION": region,
                }
            )
            cache["tencent_cloud"] = sig
            _save_cache(cache)
            return
        print(f"{t('fail')} [{result.error_code}]: {result.detail}")
        if input(t("retry")).strip().lower() in ("n", "no"):
            sys.exit(1)


def _step_trtc(cache: Dict[str, str], report: Dict[str, dict]) -> None:
    print()
    print(t("step_trtc"))
    # Read previously configured Tencent Cloud credentials for real OpenAPI validation
    tc_cred = TencentCloudCredential(
        secret_id=os.getenv("TENCENT_CLOUD_SECRET_ID", "")
        or _read_env_value("TENCENT_CLOUD_SECRET_ID"),
        secret_key=os.getenv("TENCENT_CLOUD_SECRET_KEY", "")
        or _read_env_value("TENCENT_CLOUD_SECRET_KEY"),
        region=_read_env_value("TENCENT_CLOUD_REGION") or "ap-guangzhou",
    )
    while True:
        app_id_raw = input(t("input_app_id")).strip()
        app_key = getpass.getpass(t("input_app_key")).strip()
        if not app_id_raw or not app_key:
            print(t("fail") + ": empty input")
            continue
        try:
            app_id = int(app_id_raw)
        except ValueError:
            print(t("fail") + ": SDKAppID must be integer")
            continue

        # —— SDKSecretKey defensive validation ——
        # TRTC SDKSecretKey is a 64-char hex string (format copied directly from trtc.io console).
        # Common error: user pastes twice → 128 chars; or pastes extra whitespace.
        if not all(c in "0123456789abcdefABCDEF" for c in app_key):
            print(
                t("fail")
                + ": SDKSecretKey only allows 0-9 / a-f characters, please re-copy from TRTC console"
            )
            continue
        if len(app_key) == 128 and app_key[:64] == app_key[64:]:
            print(
                "  ⚠ Detected SDKSecretKey pasted twice (128 chars = same string copied twice), "
                "auto-truncated to first 64 characters"
            )
            app_key = app_key[:64]
        if len(app_key) != 64:
            print(
                f"{t('fail')}: SDKSecretKey must be 64 characters (you entered {len(app_key)}), "
                "please re-copy"
            )
            continue

        sig = _hash(f"{app_id}:{app_key}")
        if cache.get("trtc") == sig:
            print(t("skip_cached"))
            return
        print(t("validating"))
        # Default to intl (trtc.io international); overseas devs don't need to select region
        result = check_trtc(
            TrtcCredential(sdk_app_id=app_id, sdk_secret_key=app_key, region="intl"),
            tencent=tc_cred if tc_cred.configured else None,
        )
        report["trtc"] = result.to_dict() | {"checked_at": int(time.time())}
        if result.ok:
            print(f"{t('ok')} (latency {result.latency_ms}ms; {result.detail or ''})")
            _persist_env(
                {
                    "TRTC_SDK_APP_ID": str(app_id),
                    "TRTC_SDK_SECRET_KEY": app_key,
                }
            )
            cache["trtc"] = sig
            _save_cache(cache)
            return
        print(f"{t('fail')} [{result.error_code}]: {result.detail}")
        if input(t("retry")).strip().lower() in ("n", "no"):
            sys.exit(1)


def _step_llm(cache: Dict[str, str], report: Dict[str, dict]) -> None:
    print()
    print(t("step_llm"))
    retries = 0
    while True:
        api_key = input(t("input_llm_key")).strip()
        api_url = input(t("input_llm_url")).strip() or "https://api.openai.com/v1/chat/completions"
        model = input(t("input_llm_model")).strip() or "gpt-4o-mini"
        if not api_key:
            print(t("fail") + ": empty input")
            continue
        sig = _hash(f"{api_key}:{api_url}:{model}")
        if cache.get("llm") == sig:
            print(t("skip_cached"))
            return
        print(t("validating"))
        result = check_llm(
            LlmCredential(api_key=api_key, api_url=api_url, model=model)
        )
        report["llm"] = result.to_dict() | {"checked_at": int(time.time())}
        if result.ok:
            print(f"{t('ok')} (latency {result.latency_ms}ms)")
            _persist_env(
                {"LLM_API_KEY": api_key, "LLM_API_URL": api_url, "LLM_MODEL": model}
            )
            cache["llm"] = sig
            _save_cache(cache)
            return
        retries += 1
        print(f"{t('fail')} [{result.error_code}]: {result.detail}")
        if retries >= 3:
            print("Reached 3 failure limit. Please check your LLM Endpoint / Key and retry.")
            sys.exit(1)
        if input(t("retry")).strip().lower() in ("n", "no"):
            sys.exit(1)


# ---------------------------------------------------------------------------
# Single-step validation subcommands (for start.sh reuse)
# ---------------------------------------------------------------------------
def _validate_tencent_cloud(args: argparse.Namespace) -> int:
    r = check_tencent_cloud(
        TencentCloudCredential(args.secret_id, args.secret_key, args.region or "ap-guangzhou")
    )
    print(json.dumps(r.to_dict()))
    return 0 if r.ok else 1


def _validate_trtc(args: argparse.Namespace) -> int:
    try:
        app_id = int(args.app_id)
    except ValueError:
        print(json.dumps({"status": "failed", "error_code": "E002", "detail": "invalid app_id"}))
        return 1
    tc = None
    if getattr(args, "secret_id", None) and getattr(args, "secret_key", None):
        tc = TencentCloudCredential(args.secret_id, args.secret_key, args.region or "ap-guangzhou")
    r = check_trtc(
        TrtcCredential(sdk_app_id=app_id, sdk_secret_key=args.app_key),
        tencent=tc,
    )
    print(json.dumps(r.to_dict()))
    return 0 if r.ok else 1


def _validate_llm(args: argparse.Namespace) -> int:
    r = check_llm(
        LlmCredential(
            api_key=args.api_key,
            api_url=args.endpoint or "https://api.openai.com/v1/chat/completions",
            model=args.model or "gpt-4o-mini",
        )
    )
    print(json.dumps(r.to_dict()))
    return 0 if r.ok else 1


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="TRTC Voice Agent credentials setup")
    parser.add_argument("--reset", action="store_true", help="Clear cache and reconfigure")
    sub = parser.add_subparsers(dest="cmd")

    p_tc = sub.add_parser("validate-tencent-cloud")
    p_tc.add_argument("--secret-id", required=True)
    p_tc.add_argument("--secret-key", required=True)
    p_tc.add_argument("--region", default="ap-guangzhou")

    p_trtc = sub.add_parser("validate-trtc")
    p_trtc.add_argument("--app-id", required=True)
    p_trtc.add_argument("--app-key", required=True)
    p_trtc.add_argument("--secret-id", default="", help="Tencent Cloud SecretId (optional, enables deep validation)")
    p_trtc.add_argument("--secret-key", default="", help="Tencent Cloud SecretKey (optional, enables deep validation)")
    p_trtc.add_argument("--region", default="ap-guangzhou")

    p_llm = sub.add_parser("validate-llm")
    p_llm.add_argument("--api-key", required=True)
    p_llm.add_argument("--endpoint", default="")
    p_llm.add_argument("--model", default="")

    args = parser.parse_args()

    if args.cmd == "validate-tencent-cloud":
        return _validate_tencent_cloud(args)
    if args.cmd == "validate-trtc":
        return _validate_trtc(args)
    if args.cmd == "validate-llm":
        return _validate_llm(args)

    if args.reset and CACHE_FILE.exists():
        CACHE_FILE.unlink()

    print(t("header"))
    cache = _load_cache()
    report: Dict[str, dict] = {}
    _step_tencent_cloud(cache, report)
    _step_trtc(cache, report)
    _step_llm(cache, report)

    REPORT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(REPORT_FILE, 0o644)
    except OSError:
        pass

    print()
    print(t("done"))
    print(t("next_step"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
