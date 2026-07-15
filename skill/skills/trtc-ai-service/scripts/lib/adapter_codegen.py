"""Three-tier fallback adapter code generator (Phase 3 Stage 4).

Input: set of ``ContractDiff`` + user's original ParsedApi set + capability directory.
Output: ``capabilities/<name>/src/adapters/user_custom.py`` (L1/L2) or
        section path pointing to ``INTERFACE_ADAPT.md`` (L3).

Design principles:
- Both L1 and L2 generate the same ``user_custom.py``; L2 just includes ``# TODO`` comments for the user to fill in
- L1 / L2 preferentially inherit from ``DefaultRest*Client`` to reuse HTTP / auth / security validation
- L3 generates no code — only outputs the section path from INTERFACE_ADAPT.md at the corresponding level
- Generated artifacts are **idempotent**: old ``user_custom.py`` is backed up as ``.bak`` before each rewrite
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .contract_resolver import (
    BusinessContract,
    ContractDiff,
    DegradeLevel,
    ExternalApi,
    FieldDiff,
)
from .curl_parser import ParsedApi


# ---------------------------------------------------------------------------
# Input aggregation
# ---------------------------------------------------------------------------
@dataclass
class ApiAdaptation:
    """单条契约的适配结果。"""

    default: ExternalApi
    user: Optional[ParsedApi]
    diff: Optional[ContractDiff]

    @property
    def level(self) -> DegradeLevel:
        if self.diff is None:
            return DegradeLevel.L1  # user did not provide → use default contract
        return self.diff.level


@dataclass
class CodegenResult:
    level: DegradeLevel
    capability: str
    artifact: str = ""               # relative path of generated file or doc path
    todos: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    enable_env: Dict[str, str] = field(default_factory=dict)  # env vars needed to enable

    def to_dict(self) -> Dict:
        return {
            "level": self.level.value,
            "capability": self.capability,
            "artifact": self.artifact,
            "todos": self.todos,
            "notes": self.notes,
            "enable_env": self.enable_env,
        }


# ---------------------------------------------------------------------------
# Code generation templates for known capability packages
# ---------------------------------------------------------------------------
_KNOWN_CAPABILITIES = {
    "human-handoff": {
        "default_adapter_class": "DefaultRestHandoffClient",
        "import_default": "from .default_rest import DefaultRestHandoffClient",
        "from_env_factory": "user_custom_from_env",
        "env_prefix": "HH_REST",
        "adapter_env": "HH_ADAPTER",
    },
    "knowledge-base": {
        "default_adapter_class": "DefaultRestKbClient",
        "import_default": "from .default_rest import DefaultRestKbClient",
        "from_env_factory": "user_custom_from_env",
        "env_prefix": "KB_REST",
        "adapter_env": "KB_ADAPTER",
    },
}


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def generate_user_custom(
    contract: BusinessContract,
    adaptations: List[ApiAdaptation],
    capability_dir: Path,
    *,
    base_url: str = "",
    auth_header: str = "",
    dry_run: bool = False,
) -> CodegenResult:
    """Infer overall level from adaptations → generate user_custom.py or return L3 guidance path."""

    levels = [a.level for a in adaptations]
    overall = max(levels, key=lambda lv: ["L1", "L2", "L3"].index(lv.value)) if levels else DegradeLevel.L1
    cap_name = contract.capability
    known = _KNOWN_CAPABILITIES.get(cap_name)
    result = CodegenResult(level=overall, capability=cap_name)

    if overall == DegradeLevel.L3 or known is None:
        sop = capability_dir / contract.customization_sop
        result.level = DegradeLevel.L3 if known is None else overall
        try:
            result.artifact = str(sop.relative_to(capability_dir.parent.parent))
        except ValueError:
            result.artifact = str(sop)
        if known is None:
            result.notes.append(
                f"Capability {cap_name} has no codegen template; implement manually per INTERFACE_ADAPT.md"
            )
        else:
            result.notes.append("Protocol-level differences; implement manually per INTERFACE_ADAPT.md §5 L3 template")
        return result

    # Render code
    code = _render_user_custom(contract, adaptations, known, base_url, auth_header)
    todos = _collect_todos(adaptations)

    target = capability_dir / "src" / "adapters" / "user_custom.py"
    target.parent.mkdir(parents=True, exist_ok=True)

    if not dry_run:
        if target.exists():
            backup = target.with_suffix(".py.bak")
            backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        target.write_text(code, encoding="utf-8")

        mapping_path = capability_dir / "src" / "adapters" / "user_custom_mapping.yaml"
        mapping_path.write_text(_render_mapping_yaml(adaptations), encoding="utf-8")

    try:
        result.artifact = str(target.relative_to(capability_dir.parent.parent))
    except ValueError:
        result.artifact = str(target)
    result.todos = todos
    result.enable_env = {
        known["adapter_env"]: "user_custom",
        f"{known['env_prefix']}_BASE_URL": base_url or "<请填写你的 API 基础 URL>",
    }
    if auth_header and auth_header.lower() != "authorization":
        result.notes.append(
            f"鉴权头 '{auth_header}' 非默认 Bearer，已在生成的 _headers() 中覆写"
        )
    if overall == DegradeLevel.L2:
        result.notes.append("生成文件包含 TODO 标注，请按 todos[] 列表逐项补完")
    return result


# ---------------------------------------------------------------------------
# Code block utilities: assemble code by "line + indent level", avoiding textwrap.dedent / f-string indent traps
# ---------------------------------------------------------------------------
INDENT = "    "  # 4 spaces


def _join_lines(lines: List[str]) -> str:
    return "\n".join(lines)


def _indent_block(text: str, level: int) -> str:
    pad = INDENT * level
    return "\n".join((pad + line) if line else "" for line in text.splitlines())


# ---------------------------------------------------------------------------
# user_custom.py full render
# ---------------------------------------------------------------------------
def _render_user_custom(
    contract: BusinessContract,
    adaptations: List[ApiAdaptation],
    known: Dict[str, str],
    base_url: str,
    auth_header: str,
) -> str:
    cap = contract.capability
    adapter_class = "UserCustomHandoffClient" if cap == "human-handoff" else "UserCustomKbClient"
    base_class = known["default_adapter_class"]
    factory_name = known["from_env_factory"]
    env_prefix = known["env_prefix"]
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    summary_lines = [f"  - {ap.default.name}: {ap.level.value}" for ap in adaptations]
    summary = "\n".join(summary_lines) if summary_lines else "  (none)"

    lines: List[str] = []
    lines.append(f'"""user_custom adapter for {cap} (auto-generated by contract-adapt.py).')
    lines.append("")
    lines.append(f"Generated at : {timestamp}")
    lines.append(f"Base URL     : {base_url or '<unset>'}")
    lines.append(f"Auth header  : {auth_header or 'Authorization (Bearer)'}")
    lines.append("")
    lines.append("Coverage summary:")
    lines.append(summary)
    lines.append("")
    lines.append("Automatically generated by ``scripts/contract-adapt.py``. Do not edit by hand; re-running creates a .bak backup.")
    lines.append('"""')
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("import os")
    lines.append("from typing import List, Optional")
    lines.append("")
    lines.append(known["import_default"])
    lines.append("")
    lines.append("")
    lines.append(f"class {adapter_class}({base_class}):")
    lines.append(f'    """L1/L2 field-mapping adapter ({cap})."""')
    lines.append("")

    # 鉴权头覆写（如有）
    if auth_header and auth_header.lower() != "authorization":
        for ln in _render_header_override(auth_header).splitlines():
            lines.append(INDENT + ln if ln else "")
        lines.append("")

    # 各方法体
    for ap in adaptations:
        method_block = (
            _render_hh_method(ap, auth_header) if cap == "human-handoff" else _render_kb_method(ap, auth_header)
        )
        if not method_block.strip():
            continue
        for ln in method_block.splitlines():
            lines.append(INDENT + ln if ln else "")
        lines.append("")

    # 工厂函数（模块级）
    lines.append("")
    lines.append(f'def {factory_name}() -> Optional["{adapter_class}"]:')
    lines.append(f'    base = os.getenv("{env_prefix}_BASE_URL")')
    lines.append("    if not base:")
    lines.append("        return None")
    lines.append(f"    return {adapter_class}(")
    lines.append("        base_url=base,")
    lines.append(f'        token=os.getenv("{env_prefix}_TOKEN"),')
    lines.append(f'        timeout_ms=int(os.getenv("{env_prefix}_TIMEOUT_MS", "5000")),')
    lines.append("    )")
    lines.append("")

    return _join_lines(lines)


def _render_header_override(auth_header: str) -> str:
    return _join_lines([
        "def _headers(self) -> dict:",
        '    h = {"Content-Type": "application/json"}',
        "    if self._token:",
        f'        h["{auth_header}"] = self._token  # 自定义鉴权头（contract-adapt 解析）',
        "    return h",
    ])


# ---------------------------------------------------------------------------
# diff → 字段映射工具
# ---------------------------------------------------------------------------
def _mapping(diff: Optional[ContractDiff], section: str) -> Dict[str, str]:
    if diff is None:
        return {}
    out: Dict[str, str] = {}
    for f in diff.fields:
        if f.kind == "rename" and f.path.startswith(section + "."):
            out[f.path.split(".", 1)[1]] = f.user
    return out


# ---------------------------------------------------------------------------
# human-handoff: 各方法渲染
# ---------------------------------------------------------------------------
def _render_hh_method(ap: ApiAdaptation, auth_header: str) -> str:
    name = ap.default.name
    if name == "ticket.create":
        return _render_hh_create(ap)
    if name == "ticket.status_query":
        return _render_hh_status(ap)
    if name == "ticket.cancel":
        return _render_hh_cancel(ap)
    return ""


def _render_hh_create(ap: ApiAdaptation) -> str:
    req_map = _mapping(ap.diff, "request") or {}
    resp_map = _mapping(ap.diff, "response") or {}
    user_path = ap.user.path if ap.user else "/tickets"
    todo_marker = "# TODO" if ap.level == DegradeLevel.L2 else "# auto-mapped"

    rid = resp_map.get("ticket_id", "ticket_id")
    rqp = resp_map.get("queue_position", "queue_position")
    reta = resp_map.get("eta_seconds", "eta_seconds")

    payload_kv: List[str] = []
    for default_field, value_expr in (
        ("user_id", "user_id"),
        ("subject", "subject"),
        ("description", "description"),
        ("priority", "priority"),
        ("transcript", "list(transcript or [])"),
    ):
        user_field = req_map.get(default_field, default_field)
        payload_kv.append(f'        "{user_field}": {value_expr},')

    return _join_lines([
        "def create_ticket(",
        "    self,",
        "    *,",
        "    user_id: str,",
        '    subject: str = "",',
        '    description: str = "",',
        '    priority: str = "normal",',
        "    transcript: Optional[List[str]] = None,",
        "):",
        "    from ..core.models import Ticket, TicketStatusEnum, now_ts",
        f"    payload = {{   {todo_marker}: 字段映射由 contract-adapt 推断",
        *payload_kv,
        "    }",
        f'    data = self._post("{user_path}", payload)',
        f'    ticket_id = str(data.get("{rid}") or "").strip()',
        "    if not ticket_id:",
        f'        raise RuntimeError("remote did not return id field {rid!r}")',
        "    return Ticket(",
        "        ticket_id=ticket_id,",
        "        user_id=user_id,",
        "        subject=subject,",
        "        description=description,",
        '        priority=priority or "normal",',
        "        status=TicketStatusEnum.PENDING.value,",
        f'        queue_position=int(data.get("{rqp}") or 0),',
        f'        eta_seconds=int(data.get("{reta}") or 0),',
        "        transcript=list(transcript or []),",
        '        reason=description[:128] if description else "",',
        "        created_at=now_ts(),",
        "        updated_at=now_ts(),",
        "    )",
    ])


def _render_hh_status(ap: ApiAdaptation) -> str:
    resp_map = _mapping(ap.diff, "response") or {}
    user_path = ap.user.path if ap.user else "/tickets/{ticket_id}"
    rid = resp_map.get("ticket_id", "ticket_id")
    rstatus = resp_map.get("status", "status")
    ragent = resp_map.get("agent_id", "agent_id")
    todo_marker = "# TODO" if ap.level == DegradeLevel.L2 else "# auto-mapped"

    # 用户路径中如果有 {ticket_id} 占位需要保留 f-string
    return _join_lines([
        "def query_status(self, ticket_id: str):",
        "    from ..core.models import TicketStatus, TicketStatusEnum",
        f'    data = self._get(f"{user_path}", optional=True)   {todo_marker}',
        "    if data is None:",
        "        return None",
        f'    status = str(data.get("{rstatus}") or TicketStatusEnum.PENDING.value)',
        "    return TicketStatus(",
        f'        ticket_id=str(data.get("{rid}") or ticket_id),',
        "        status=status,",
        f'        agent_id=data.get("{ragent}"),',
        '        updated_at=float(data.get("updated_at") or 0.0) or None,',
        "    )",
    ])


def _render_hh_cancel(ap: ApiAdaptation) -> str:
    req_map = _mapping(ap.diff, "request") or {}
    user_path = ap.user.path if ap.user else "/tickets/{ticket_id}/cancel"
    rid_field = req_map.get("ticket_id", "ticket_id")
    reason_field = req_map.get("reason", "reason")
    todo_marker = "# TODO" if ap.level == DegradeLevel.L2 else "# auto-mapped"

    return _join_lines([
        'def cancel_ticket(self, ticket_id: str, reason: str = ""):',
        "    from ..core.models import Ticket, TicketStatusEnum, now_ts",
        f"    data = self._post(   {todo_marker}",
        f'        f"{user_path}",',
        f'        {{"{rid_field}": ticket_id, "{reason_field}": reason}},',
        "        optional=True,",
        "    )",
        "    if data is None:",
        "        return None",
        "    return Ticket(",
        "        ticket_id=ticket_id,",
        '        user_id="",',
        "        status=TicketStatusEnum.CANCELED.value,",
        "        reason=reason,",
        "        updated_at=now_ts(),",
        "        closed_at=now_ts(),",
        "    )",
    ])


# ---------------------------------------------------------------------------
# knowledge-base: 各方法渲染
# ---------------------------------------------------------------------------
def _render_kb_method(ap: ApiAdaptation, auth_header: str) -> str:
    name = ap.default.name
    todo_marker = "# TODO" if ap.level == DegradeLevel.L2 else "# auto-mapped"
    if name == "faq.search":
        req_map = _mapping(ap.diff, "request") or {}
        q = req_map.get("query", "query")
        topk = req_map.get("top_k", "top_k")
        path = ap.user.path if ap.user else "/faq/search"
        return _join_lines([
            "def search(self, query: str, *, top_k: Optional[int] = None, min_score: Optional[float] = None):",
            "    from ..core.models import SearchHit, FaqEntry",
            f'    payload = {{"{q}": query, "{topk}": top_k or 3}}   {todo_marker}',
            f'    data = self._post("{path}", payload)',
            '    hits = data.get("hits") or [] if isinstance(data, dict) else (data or [])',
            "    out: List[SearchHit] = []",
            "    for h in hits:",
            '        entry_data = h.get("entry") if isinstance(h, dict) else None',
            "        if not isinstance(entry_data, dict):",
            "            continue",
            "        out.append(SearchHit(",
            "            entry=FaqEntry(",
            '                id=str(entry_data.get("id", "")),',
            '                question=str(entry_data.get("question", "")),',
            '                answer=str(entry_data.get("answer", "")),',
            '                keywords=list(entry_data.get("keywords") or []),',
            "            ),",
            '            score=float(h.get("score") or 0.0),',
            "        ))",
            "    return out",
        ])
    if name == "faq.list":
        path = ap.user.path if ap.user else "/faq"
        return _join_lines([
            "def list_all(self):",
            "    from ..core.models import FaqEntry",
            f'    data = self._get("{path}")   {todo_marker}',
            '    items = data.get("items") if isinstance(data, dict) else data',
            "    return [FaqEntry(",
            '        id=str(it.get("id", "")),',
            '        question=str(it.get("question", "")),',
            '        answer=str(it.get("answer", "")),',
            '        keywords=list(it.get("keywords") or []),',
            "    ) for it in (items or [])]",
        ])
    if name == "faq.upsert":
        path = ap.user.path if ap.user else "/faq"
        return _join_lines([
            "def upsert(self, entry):",
            "    from ..core.models import FaqEntry",
            f"    payload = {{   {todo_marker}",
            '        "id": entry.id,',
            '        "question": entry.question,',
            '        "answer": entry.answer,',
            '        "keywords": list(entry.keywords or []),',
            "    }",
            f'    data = self._post("{path}", payload)',
            "    return FaqEntry(",
            '        id=str(data.get("id", entry.id)),',
            '        question=str(data.get("question", entry.question)),',
            '        answer=str(data.get("answer", entry.answer)),',
            '        keywords=list(data.get("keywords") or entry.keywords or []),',
            "    )",
        ])
    if name == "faq.delete":
        path = ap.user.path if ap.user else "/faq/{entry_id}"
        return _join_lines([
            "def delete(self, entry_id: str) -> bool:",
            f'    url = self._base + f"{path}"   {todo_marker}',
            "    resp = self._session.delete(url, headers=self._headers(), timeout=self._timeout)",
            "    if resp.status_code == 404:",
            "        return False",
            "    if resp.status_code >= 400:",
            '        raise RuntimeError(f"remote kb service returned HTTP {resp.status_code}")',
            "    return True",
        ])
    return ""


# ---------------------------------------------------------------------------
# mapping.yaml & todos
# ---------------------------------------------------------------------------
def _render_mapping_yaml(adaptations: List[ApiAdaptation]) -> str:
    out = ["# 由 scripts/contract-adapt.py 自动生成；左 = 默认契约字段，右 = 用户实际字段", ""]
    for ap in adaptations:
        out.append(f"{ap.default.name}:")
        if ap.diff is None:
            out.append("  # 用户未提供；使用默认契约")
            continue
        for section in ("request", "response"):
            section_map = _mapping(ap.diff, section)
            if section_map:
                out.append(f"  {section}:")
                for d, u in section_map.items():
                    out.append(f"    {d}: {u}")
        out.append(f"  level: {ap.level.value}")
    return "\n".join(out) + "\n"


def _collect_todos(adaptations: List[ApiAdaptation]) -> List[str]:
    todos: List[str] = []
    for ap in adaptations:
        if ap.level != DegradeLevel.L2 or ap.diff is None:
            continue
        for f in ap.diff.fields:
            if not f.in_slot and f.kind in ("rename", "type_mismatch", "missing_in_user"):
                todos.append(
                    f"[{ap.default.name}] {f.path}: {f.kind} default={f.default!r} user={f.user!r}"
                )
        if ap.diff.protocol_mismatch:
            todos.append(f"[{ap.default.name}] protocol: {ap.diff.protocol_reason}")
    return todos
