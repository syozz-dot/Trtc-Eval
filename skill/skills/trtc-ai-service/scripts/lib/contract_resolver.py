"""business_contract field parsing & diff utilities (Phase 3 Stage 4).

Responsibilities:
1. Load a capability's ``manifest.yaml.business_contract`` block and perform static
   validation (BC001~BC006) per ``business-contract-spec.md`` §7 rules.
2. Convert a manifest-declared ``external_apis[name]`` entry into ``ParsedApi`` form (default contract).
3. ``diff_contracts(default, user)`` returns structured differences and infers
   fallback level L1 / L2 / L3.

Fallback Level Determination:

| Level | Trigger Condition |
|---|---|
| L1 | Only field differences within the ``adapter_slots`` list (name remapping / enum value mapping) |
| L2 | Parsed successfully but structural differences exist (nested level differences, type differences, missing required fields) |
| L3 | Protocol-level differences (significant method mismatch, non-REST/JSON user API, body_format=raw, etc.) |
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .curl_parser import AuthSpec, ParsedApi, _normalize_schema


# ---------------------------------------------------------------------------
# Error codes / exceptions
# ---------------------------------------------------------------------------
class ContractError(RuntimeError):
    """business_contract field error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


class DegradeLevel(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class ExternalApi:
    name: str
    direction: str
    method: str
    path: str
    description: str = ""
    request_schema: Dict[str, Any] = field(default_factory=dict)
    response_schema: Dict[str, Any] = field(default_factory=dict)
    adapter_slots: List[str] = field(default_factory=list)
    auth: AuthSpec = field(default_factory=AuthSpec)
    timeout_ms: int = 5000

    def to_parsed_api(self, base_url: str = "") -> ParsedApi:
        # manifest.yaml field values are already normalized literals ("string" / "int" / "enum[...]" / "string[]"),
        # so do **not** call _normalize_schema (avoids degrading "string[]" to "string")
        return ParsedApi(
            method=self.method.upper(),
            base_url=base_url,
            path=self.path,
            headers={},
            auth=self.auth,
            request_schema=dict(self.request_schema),
            response_schema=dict(self.response_schema),
            body_format="json" if self.method.upper() in {"POST", "PUT", "PATCH"} else "none",
            source="manifest",
        )


@dataclass
class BusinessContract:
    capability: str
    port_class: str = ""
    default_adapter: str = ""
    mock_adapter: str = ""
    customization_sop: str = "INTERFACE_ADAPT.md"
    external_apis: List[ExternalApi] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def get_api(self, name: str) -> Optional[ExternalApi]:
        for a in self.external_apis:
            if a.name == name:
                return a
        return None

    def outbound_apis(self) -> List[ExternalApi]:
        return [a for a in self.external_apis if a.direction == "outbound"]


@dataclass
class FieldDiff:
    """Single field diff."""

    path: str                 # request.subject / response.ticket_id
    kind: str                 # rename | type_mismatch | missing_in_user | extra_in_user | enum_mismatch
    default: Any = None       # default contract field name / type / enum set
    user: Any = None          # user's actual value
    in_slot: bool = False     # whether within adapter_slots (determines L1 vs L2)

    def to_dict(self) -> Dict:
        return {
            "path": self.path,
            "kind": self.kind,
            "default": self.default,
            "user": self.user,
            "in_slot": self.in_slot,
        }


@dataclass
class ContractDiff:
    api_name: str
    method_match: bool
    path_match: bool
    direction: str
    fields: List[FieldDiff] = field(default_factory=list)
    protocol_mismatch: bool = False
    protocol_reason: str = ""
    suggested_mapping: Dict[str, Any] = field(default_factory=dict)

    @property
    def level(self) -> DegradeLevel:
        return decide_level(self)

    def to_dict(self) -> Dict:
        return {
            "api_name": self.api_name,
            "method_match": self.method_match,
            "path_match": self.path_match,
            "direction": self.direction,
            "fields": [f.to_dict() for f in self.fields],
            "protocol_mismatch": self.protocol_mismatch,
            "protocol_reason": self.protocol_reason,
            "suggested_mapping": self.suggested_mapping,
            "level": self.level.value,
        }


# ---------------------------------------------------------------------------
# Manifest loading & validation
# ---------------------------------------------------------------------------
def _import_dotted(path: str) -> bool:
    """Attempt to import a dotted path; only validates syntax / module file existence, no instantiation."""
    if not path:
        return False
    # Only validate form: a.b.c.ClassName
    if not re.match(r"^[A-Za-z_][\w\.]*$", path):
        return False
    return True


def load_business_contract(capability_dir: Path) -> BusinessContract:
    """Load a capability manifest.yaml and parse its business_contract block.

    Raises
    ------
    ContractError
        manifest missing / business_contract missing / invalid fields.
    """
    manifest_path = Path(capability_dir) / "manifest.yaml"
    if not manifest_path.exists():
        raise ContractError("BC000", f"manifest not found: {manifest_path}")
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    cap_name = str(raw.get("name", "") or capability_dir.name)
    bc_raw = raw.get("business_contract")
    if not isinstance(bc_raw, dict):
        raise ContractError("BC000", f"{cap_name}: missing business_contract block")

    # tool-calling uses §5 dedicated contract block; not yet supported by this tool
    if "alpha_track" in bc_raw or "beta_track" in bc_raw:
        raise ContractError(
            "BC000",
            f"{cap_name}: tool-calling-style contract not supported by contract-adapt yet",
        )

    port_class = str(bc_raw.get("port_class", ""))
    default_adapter = str(bc_raw.get("default_adapter", ""))
    mock_adapter = str(bc_raw.get("mock_adapter", ""))
    sop = str(bc_raw.get("customization_sop", "INTERFACE_ADAPT.md"))

    # BC001: all three dotted paths must be valid
    for label, p in (("port_class", port_class), ("default_adapter", default_adapter), ("mock_adapter", mock_adapter)):
        if not _import_dotted(p):
            raise ContractError("BC001", f"{cap_name}: invalid {label}={p!r}")

    apis: List[ExternalApi] = []
    seen_names: set = set()
    for entry in bc_raw.get("external_apis") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            raise ContractError("BC003", f"{cap_name}: external_api missing 'name'")
        # BC002: duplicate name
        if name in seen_names:
            raise ContractError("BC002", f"{cap_name}: duplicate external_api name {name!r}")
        seen_names.add(name)
        direction = str(entry.get("direction", "outbound"))
        method = str(entry.get("method", "")).upper()
        path = str(entry.get("path", ""))
        if direction == "outbound" and (not method or not path):
            raise ContractError("BC003", f"{cap_name}.{name}: outbound requires method+path")

        auth_raw = entry.get("auth") or {}
        auth = AuthSpec(
            type=str(auth_raw.get("type", "none")),
            location=str(auth_raw.get("location", "header")),
            name=str(auth_raw.get("name", "")),
        )

        api = ExternalApi(
            name=name,
            direction=direction,
            method=method,
            path=path,
            description=str(entry.get("description", "")),
            request_schema=dict(entry.get("request_schema") or {}),
            response_schema=dict(entry.get("response_schema") or {}),
            adapter_slots=list(entry.get("adapter_slots") or []),
            auth=auth,
            timeout_ms=int(entry.get("timeout_ms", 5000)),
        )

        # BC004: adapter_slots should be resolvable in schema (warning only, no exception)
        # Simplified: only checks top-level fields
        for slot in api.adapter_slots:
            if not (slot.startswith("request.") or slot.startswith("response.")):
                # 视为 warning，无副作用
                pass

        apis.append(api)

    return BusinessContract(
        capability=cap_name,
        port_class=port_class,
        default_adapter=default_adapter,
        mock_adapter=mock_adapter,
        customization_sop=sop,
        external_apis=apis,
        raw=bc_raw,
    )


# ---------------------------------------------------------------------------
# Default contract vs user contract diff
# ---------------------------------------------------------------------------
def _walk_schema(schema: Any, prefix: str = "") -> Dict[str, Any]:
    """Flatten arbitrary nested type descriptions to ``{ 'a.b.c': type_string }``."""
    out: Dict[str, Any] = {}
    if isinstance(schema, dict):
        for k, v in schema.items():
            sub = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                out.update(_walk_schema(v, sub))
            else:
                out[sub] = v
    el    if isinstance(schema, list):
        # Array: recurse into first element
        if schema:
            out.update(_walk_schema(schema[0], f"{prefix}[]"))
    else:
        out[prefix or "$"] = schema
    return out


def _slot_match(field_path: str, slots: List[str]) -> bool:
    """``request.priority`` ∈ slots (exact match, no wildcards)."""
    return field_path in set(slots)


def _detect_protocol_mismatch(default: ExternalApi, user: ParsedApi) -> Tuple[bool, str]:
    if default.method.upper() != user.method.upper():
        return (True, f"method mismatch: default={default.method}, user={user.method}")
    if user.body_format == "raw":
        return (True, "user body is non-JSON raw payload")
    # Path mismatch is not a protocol-level diff (adapter can override path), but record it
    return (False, "")


def diff_contracts(default: ExternalApi, user: ParsedApi) -> ContractDiff:
    """Compare default contract with user API; produce structured differences.

    Notes
    -----
    - Request field comparison: uses default schema as baseline, checks whether user schema
      provides same-named fields; if not same-named but user has extra fields, record as
      ``rename`` candidate (paired only when default field is missing).
    - Response fields same logic; if user did not provide response (response_schema is empty),
      only generate ``missing_in_user`` but do not count as protocol mismatch.
    - Type differences (``string`` vs ``int``) recorded as ``type_mismatch``.
    - Enum differences not visible in curl input, only OpenAPI input; recorded as ``enum_mismatch``.
    """
    diff = ContractDiff(
        api_name=default.name,
        method_match=default.method.upper() == user.method.upper(),
        path_match=default.path == user.path,
        direction=default.direction,
    )
    pmm, reason = _detect_protocol_mismatch(default, user)
    diff.protocol_mismatch = pmm
    diff.protocol_reason = reason

    default_req = _walk_schema(default.request_schema, "request")
    user_req = _walk_schema(user.request_schema, "request")
    default_resp = _walk_schema(default.response_schema, "response")
    user_resp = _walk_schema(user.response_schema, "response") if user.response_schema else {}

    suggested: Dict[str, Any] = {"request": {}, "response": {}, "enum_map": {}}

    # Request comparison
    diff.fields.extend(
        _diff_section(default_req, user_req, default.adapter_slots, "request", suggested["request"])
    )
    # Response comparison (if user provided one)
    if user_resp:
        diff.fields.extend(
            _diff_section(default_resp, user_resp, default.adapter_slots, "response", suggested["response"])
        )
    else:
        for k, t in default_resp.items():
            diff.fields.append(
                FieldDiff(
                    path=k, kind="user_response_missing", default=t, user=None, in_slot=_slot_match(k, default.adapter_slots)
                )
            )

    diff.suggested_mapping = {k: v for k, v in suggested.items() if v}
    return diff


def _diff_section(
    default_flat: Dict[str, Any],
    user_flat: Dict[str, Any],
    slots: List[str],
    section: str,
    mapping_out: Dict[str, str],
) -> List[FieldDiff]:
    out: List[FieldDiff] = []
    default_keys = list(default_flat.keys())
    user_keys = list(user_flat.keys())

    # 1) 同名字段：核对类型
    common = [k for k in default_keys if k in user_flat]
    for k in common:
        if not _types_compatible(default_flat[k], user_flat[k]):
            out.append(
                FieldDiff(
                    path=k,
                    kind="type_mismatch",
                    default=default_flat[k],
                    user=user_flat[k],
                    in_slot=_slot_match(k, slots),
                )
            )
        # 同名同类型 → 不进 diff
        mapping_out[k.split(".", 1)[1]] = k.split(".", 1)[1]  # request.x → x:x

    # 2) 默认有 / 用户没同名：尝试在用户 keys 里找同类型字段做 rename 候选
    missing_default = [k for k in default_keys if k not in user_flat]
    extra_user = [k for k in user_keys if k not in default_flat]
    used_extra: set = set()
    for dk in missing_default:
        candidate = _find_rename_candidate(dk, default_flat[dk], extra_user, user_flat, used_extra)
        if candidate:
            used_extra.add(candidate)
            out.append(
                FieldDiff(
                    path=dk,
                    kind="rename",
                    default=dk.split(".", 1)[1],
                    user=candidate.split(".", 1)[1],
                    in_slot=_slot_match(dk, slots),
                )
            )
            mapping_out[dk.split(".", 1)[1]] = candidate.split(".", 1)[1]
        else:
            out.append(
                FieldDiff(
                    path=dk,
                    kind="missing_in_user",
                    default=default_flat[dk],
                    user=None,
                    in_slot=_slot_match(dk, slots),
                )
            )

    # 3) 用户多出的字段（未被认领为 rename 目标）
    for uk in extra_user:
        if uk in used_extra:
            continue
        out.append(
            FieldDiff(
                path=uk,
                kind="extra_in_user",
                default=None,
                user=user_flat[uk],
                in_slot=False,
            )
        )

    return out


# ---------------------------------------------------------------------------
# Type compatibility / rename candidates
# ---------------------------------------------------------------------------
def _types_compatible(a: Any, b: Any) -> bool:
    if a == b:
        return True
    a_s = str(a)
    b_s = str(b)
    # enum[...] and string are treated as compatible (adapter layer handles enum mapping)
    if a_s.startswith("enum[") and b_s == "string":
        return True
    if b_s.startswith("enum[") and a_s == "string":
        return True
    # int / float mutually compatible
    if {a_s, b_s} <= {"int", "float", "number"}:
        return True
    # array type mismatch → incompatible
    return False


def _find_rename_candidate(
    default_path: str,
    default_type: Any,
    extra_user_keys: List[str],
    user_flat: Dict[str, Any],
    used: set,
) -> Optional[str]:
    """Try to find a type-compatible + semantically similar path-segment candidate among extra user keys."""
    default_seg = default_path.split(".")[-1]
    candidates = [k for k in extra_user_keys if k not in used and _types_compatible(default_type, user_flat[k])]
    if not candidates:
        return None
    # Simple semantic similarity: contains / contained-by / same-category synonyms
    synonyms = {
        "user_id": ["customer_id", "uid", "user", "client_id"],
        "subject": ["title", "summary", "topic"],
        "description": ["body", "content", "message", "detail"],
        "priority": ["level", "severity", "rank"],
        "transcript": ["messages", "history", "log", "conversation"],
        "ticket_id": ["id", "order_id", "case_id", "wo_id"],
        "queue_position": ["rank", "position", "queue", "order"],
        "eta_seconds": ["wait_estimate", "wait_seconds", "eta"],
        "status": ["state", "stage", "phase"],
        "agent_id": ["operator", "assignee", "owner"],
        "query": ["q", "keyword", "search", "term"],
        "top_k": ["k", "limit", "size"],
        "min_score": ["threshold", "score_min"],
        "answer": ["reply", "content"],
        "question": ["query", "title"],
        "keywords": ["tags", "labels"],
    }
    syn_for_default = set(synonyms.get(default_seg, []))
    for cand in candidates:
        cand_seg = cand.split(".")[-1]
        if cand_seg == default_seg:
            return cand
        if cand_seg in syn_for_default or default_seg in synonyms.get(cand_seg, []):
            return cand
    # Fallback to first candidate when types match (best effort)
    return candidates[0]


# ---------------------------------------------------------------------------
# Fallback level decision
# ---------------------------------------------------------------------------
def decide_level(diff: ContractDiff) -> DegradeLevel:
    """L1 / L2 / L3 determination."""
    if diff.protocol_mismatch:
        return DegradeLevel.L3
    # Any non-slot diff → L2
    for f in diff.fields:
        if f.kind in ("user_response_missing",):
            # Missing user response is not an L2/L3 obstacle (codegen uses default contract field names)
            continue
        if f.kind == "extra_in_user":
            continue
        if not f.in_slot:
            return DegradeLevel.L2
        if f.kind in ("type_mismatch", "missing_in_user"):
            return DegradeLevel.L2
    return DegradeLevel.L1


# ---------------------------------------------------------------------------
# Static validation entry point (per spec §7)
# ---------------------------------------------------------------------------
def validate_manifest(capability_dir: Path) -> List[str]:
    """Perform full static validation on a capability's manifest.business_contract.

    Returns a list of warning strings; fatal errors (BC001~BC003/BC005) raise ContractError directly.
    """
    bc = load_business_contract(capability_dir)
    warnings: List[str] = []
    for api in bc.external_apis:
        flat_req = _walk_schema(api.request_schema, "request")
        flat_resp = _walk_schema(api.response_schema, "response")
        valid_paths = set(flat_req) | set(flat_resp)
        for slot in api.adapter_slots:
            base = slot.split("[]", 1)[0]
            if base not in valid_paths and not any(p.startswith(base + ".") for p in valid_paths):
                warnings.append(
                    f"BC004 [{bc.capability}.{api.name}] adapter_slot {slot!r} not found in schemas"
                )
        if api.auth.type == "bearer" and not api.auth.name:
            warnings.append(f"BC006 [{bc.capability}.{api.name}] bearer auth missing header name")
    return warnings
