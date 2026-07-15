#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capability contract adapter (Phase 3 Stage 4).

Adapts the user's existing system interfaces (curl or OpenAPI) to the capability's default contract,
generates ``capabilities/<name>/src/adapters/user_custom.py``, with L1/L2/L3 three-tier fallback.

Usage
-----
    # 1) Show the current default contract for a capability
    python3 scripts/contract-adapt.py human-handoff --show-default --json

    # 2) Align a single API using a curl file
    python3 scripts/contract-adapt.py human-handoff \
        --api-name ticket.create \
        --curl-file /tmp/user_create.curl \
        --base-url https://crm.example.com \
        --apply --json

    # 3) Align an entire capability using an OpenAPI file (all outbound APIs at once)
    python3 scripts/contract-adapt.py knowledge-base \
        --openapi-file /tmp/user-faq.yaml \
        --apply --json

    # 4) dry-run (no files written)
    python3 scripts/contract-adapt.py human-handoff \
        --curl-file /tmp/x.curl --json   # omit --apply for dry-run

Security Constraints
--------------------
- User API descriptions only accept **file paths**; inline input is not allowed (avoids shell history logging tokens)
- Generated code is automatically backed up as ``user_custom.py.bak``
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.lib import adapter_codegen as cg  # noqa: E402
from scripts.lib import contract_resolver as cr  # noqa: E402
from scripts.lib import curl_parser as cp  # noqa: E402
from scripts.lib import openapi_parser as op  # noqa: E402


# ---------------------------------------------------------------------------
# Output utilities
# ---------------------------------------------------------------------------
def _emit(payload: Dict, json_mode: bool) -> None:
    if json_mode:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
        sys.stdout.flush()
    else:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")


def _emit_error(message: str, json_mode: bool, *, code: str = "GENERAL") -> int:
    _emit({"ok": False, "error": code, "message": message}, json_mode)
    return 1


# ---------------------------------------------------------------------------
# Default contract display
# ---------------------------------------------------------------------------
def _show_default(contract: cr.BusinessContract, json_mode: bool) -> int:
    payload = {
        "ok": True,
        "capability": contract.capability,
        "port_class": contract.port_class,
        "default_adapter": contract.default_adapter,
        "mock_adapter": contract.mock_adapter,
        "customization_sop": contract.customization_sop,
        "outbound_apis": [
            {
                "name": a.name,
                "method": a.method,
                "path": a.path,
                "description": a.description,
                "request_schema": a.request_schema,
                "response_schema": a.response_schema,
                "adapter_slots": a.adapter_slots,
                "auth": a.auth.to_dict(),
                "timeout_ms": a.timeout_ms,
            }
            for a in contract.outbound_apis()
        ],
    }
    _emit(payload, json_mode)
    return 0


# ---------------------------------------------------------------------------
# User API loading
# ---------------------------------------------------------------------------
def _load_user_apis(
    *,
    curl_file: Optional[Path],
    openapi_file: Optional[Path],
    api_name: Optional[str],
) -> Tuple[List[cp.ParsedApi], List[str]]:
    """Return (user ParsedApi list, warnings); the caller decides how to pair them with the default contract."""
    warnings: List[str] = []
    apis: List[cp.ParsedApi] = []

    if curl_file:
        if not curl_file.exists():
            raise FileNotFoundError(f"curl file not found: {curl_file}")
        text = curl_file.read_text(encoding="utf-8")
        try:
            apis.append(cp.parse_curl_with_response(text))
        except cp.CurlParseError as exc:
            raise RuntimeError(f"curl parse failed: {exc}") from exc

    if openapi_file:
        if not openapi_file.exists():
            raise FileNotFoundError(f"openapi file not found: {openapi_file}")
        try:
            ops = op.parse_openapi(openapi_file)
        except op.OpenApiParseError as exc:
            raise RuntimeError(f"openapi parse failed: {exc}") from exc
        if not ops:
            warnings.append("openapi file contains no operations")
        apis.extend(ops)

    return apis, warnings


# ---------------------------------------------------------------------------
# pairing: match user APIs with the default contract's outbound apis
# ---------------------------------------------------------------------------
def _pair_apis(
    contract: cr.BusinessContract,
    user_apis: List[cp.ParsedApi],
    explicit_name: Optional[str],
) -> List[cg.ApiAdaptation]:
    outbound = contract.outbound_apis()
    out: List[cg.ApiAdaptation] = []

    if explicit_name:
        target = contract.get_api(explicit_name)
        if target is None:
            raise ValueError(f"no api named {explicit_name!r} in contract {contract.capability}")
        # explicit name → pair with the first user api
        if not user_apis:
            return [cg.ApiAdaptation(default=target, user=None, diff=None)]
        diff = cr.diff_contracts(target, user_apis[0])
        return [cg.ApiAdaptation(default=target, user=user_apis[0], diff=diff)]

    # auto pairing: match by method + path suffix similarity
    paired: Dict[str, cp.ParsedApi] = {}
    used: set = set()
    for default_api in outbound:
        match = _best_match(default_api, user_apis, used)
        if match is not None:
            paired[default_api.name] = match
            used.add(id(match))

    for default_api in outbound:
        user_api = paired.get(default_api.name)
        if user_api is None:
            out.append(cg.ApiAdaptation(default=default_api, user=None, diff=None))
        else:
            diff = cr.diff_contracts(default_api, user_api)
            out.append(cg.ApiAdaptation(default=default_api, user=user_api, diff=diff))
    return out


def _best_match(
    default_api: cr.ExternalApi,
    user_apis: List[cp.ParsedApi],
    used: set,
) -> Optional[cp.ParsedApi]:
    """Simple match: method must match; best path tail similarity wins."""
    candidates = [u for u in user_apis if id(u) not in used and u.method.upper() == default_api.method.upper()]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # best path tail semantic similarity
    default_tail = default_api.path.rstrip("/").rsplit("/", 1)[-1] or default_api.path
    best = candidates[0]
    best_score = -1
    for c in candidates:
        c_tail = c.path.rstrip("/").rsplit("/", 1)[-1] or c.path
        score = _similarity(default_tail, c_tail)
        if score > best_score:
            best_score = score
            best = c
    return best


def _similarity(a: str, b: str) -> int:
    a_low = a.lower()
    b_low = b.lower()
    if a_low == b_low:
        return 100
    if a_low in b_low or b_low in a_low:
        return 60
    common = set(a_low) & set(b_low)
    return len(common)


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="contract-adapt",
        description="Capability contract adaptation (curl / OpenAPI → user_custom.py)",
    )
    parser.add_argument("capability", help="Capability name (subdirectory under capabilities/)")
    parser.add_argument("--curl-file", type=Path, default=None, help="User API curl file path")
    parser.add_argument(
        "--openapi-file",
        type=Path,
        default=None,
        help="User API OpenAPI YAML / JSON file path",
    )
    parser.add_argument(
        "--api-name",
        default="",
        help="Align only the specified contract name (e.g., ticket.create); default attempts to auto-pair all outbound APIs",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Default base_url hint written into user_custom.py (not hardcoded)",
    )
    parser.add_argument(
        "--auth-header",
        default="",
        help="Override auth header name (e.g., X-Auth-Token); defaults to Authorization if empty",
    )
    parser.add_argument(
        "--show-default",
        action="store_true",
        help="Print the current default contract list without adapting",
    )
    parser.add_argument("--apply", action="store_true", help="Write generated code to file (default is dry-run)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv)

    json_mode = args.json
    cap_dir = _ROOT / "capabilities" / args.capability
    if not cap_dir.exists():
        return _emit_error(
            f"capability not found: {cap_dir}", json_mode, code="CAP_NOT_FOUND"
        )

    # 1) Load default contract
    try:
        contract = cr.load_business_contract(cap_dir)
    except cr.ContractError as exc:
        return _emit_error(str(exc), json_mode, code=exc.code)

    if args.show_default:
        return _show_default(contract, json_mode)

    if not args.curl_file and not args.openapi_file:
        return _emit_error(
            "must provide --curl-file or --openapi-file (or use --show-default)",
            json_mode,
            code="MISSING_INPUT",
        )

    # 2) Load user API
    try:
        user_apis, warnings = _load_user_apis(
            curl_file=args.curl_file,
            openapi_file=args.openapi_file,
            api_name=args.api_name or None,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _emit_error(str(exc), json_mode, code="PARSE_FAILED")

    if not user_apis:
        return _emit_error("no user API parsed", json_mode, code="EMPTY_INPUT")

    # 3) Pairing & diff
    try:
        adaptations = _pair_apis(contract, user_apis, args.api_name or None)
    except ValueError as exc:
        return _emit_error(str(exc), json_mode, code="PAIRING_FAILED")

    # 4) Static manifest validation (warnings only in payload)
    manifest_warnings = cr.validate_manifest(cap_dir)

    # 5) Code generation
    result = cg.generate_user_custom(
        contract,
        adaptations,
        cap_dir,
        base_url=args.base_url,
        auth_header=args.auth_header,
        dry_run=not args.apply,
    )

    payload: Dict = {
        "ok": True,
        "capability": contract.capability,
        "level": result.level.value,
        "artifact": result.artifact,
        "todos": result.todos,
        "notes": result.notes,
        "enable_env": result.enable_env,
        "warnings": warnings + manifest_warnings,
        "applied": args.apply,
        "adaptations": [
            {
                "api_name": a.default.name,
                "level": a.level.value,
                "method_match": (a.diff.method_match if a.diff else True),
                "path_match": (a.diff.path_match if a.diff else True),
                "diff": a.diff.to_dict() if a.diff else None,
                "user_api": a.user.to_dict() if a.user else None,
            }
            for a in adaptations
        ],
    }
    _emit(payload, json_mode)
    return 0 if result.level != cr.DegradeLevel.L3 else 0  # L3 also exits normally; AI decides next step


if __name__ == "__main__":
    sys.exit(main())
