"""Execute / plan code injection per manifest injection point descriptions.

The position field uses three unified formats (P2 standardized spec):
    before:<function_name>     Insert before the specified function definition
    after:<function_name>      Insert after the specified function definition
    replace:<function_name>    Replace the specified function

For cross-language compatibility, matching uses relaxed "line-level + function keyword" heuristics:
    Python:    def func_name(...)        / class func_name(
    JS/TS:     function func_name(... )  / func_name = (...) =>
    Java:      \\bfunc_name\\s*\\(

The skeleton conversation-core injection points are currently only declared in .py source,
so this module's default implementation is Python-focused. Injection for other languages
only returns "suggested patches" for the Agent to apply.

API:
    plan(injection_points, extensions, source_root) -> List[InjectionPlan]
    apply_plans(plans, dry_run=True) -> List[ApplyResult]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass
class InjectionPoint:
    id: str
    target: str          # 相对于骨架根的源文件路径
    position: str        # before:xxx / after:xxx / replace:xxx
    description: str = ""


@dataclass
class Extension:
    inject_at: str           # 引用 InjectionPoint.id
    code_template: str = ""  # 模板路径，相对能力包根
    inline_code: str = ""    # 直接以字符串形式提供的代码
    capability: str = ""     # 来源能力包名（拼装日志使用）


@dataclass
class InjectionPlan:
    point: InjectionPoint
    extension: Extension
    target_abs_path: Path
    op: str                  # before | after | replace
    anchor: str              # 函数 / 类名
    code: str                # 真正注入的代码片段
    valid: bool = True
    error: str = ""


@dataclass
class ApplyResult:
    plan: InjectionPlan
    applied: bool
    dry_run: bool
    diff_preview: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------
_POSITION_RE = re.compile(r"^(before|after|replace):(.+)$")


def _parse_position(position: str) -> Optional[tuple]:
    m = _POSITION_RE.match(position.strip())
    if not m:
        return None
    return m.group(1), m.group(2).strip()


def _load_template(capability_root: Path, ext: Extension) -> str:
    if ext.inline_code:
        return ext.inline_code
    if ext.code_template:
        p = capability_root / ext.code_template
        if p.exists():
            return p.read_text(encoding="utf-8")
    return ""


def plan(
    skeleton_root: Path,
    injection_points: List[Dict],
    capabilities: List[tuple],
) -> List[InjectionPlan]:
    """构造注入计划。

    Parameters
    ----------
    skeleton_root
        conversation-core 根目录（用于解析 target 相对路径）。
    injection_points
        骨架 manifest 声明的 injection_points 列表（dict 形式）。
    capabilities
        list of (capability_root: Path, extensions: List[dict])
    """
    points: Dict[str, InjectionPoint] = {}
    for raw in injection_points:
        if not raw.get("id") or not raw.get("position") or not raw.get("target"):
            continue
        points[raw["id"]] = InjectionPoint(
            id=raw["id"],
            target=raw["target"],
            position=raw["position"],
            description=raw.get("description", ""),
        )

    plans: List[InjectionPlan] = []
    for cap_root, exts in capabilities:
        for raw in exts or []:
            inject_id = raw.get("inject_at")
            if not inject_id or inject_id not in points:
                # 引用未知点：放一条无效计划，由 resolver 阶段已拦截，这里兜底
                plans.append(
                    InjectionPlan(
                        point=InjectionPoint(id=inject_id or "?", target="", position=""),
                        extension=Extension(
                            inject_at=inject_id or "",
                            code_template=raw.get("code_template", ""),
                            inline_code=raw.get("inline_code", ""),
                            capability=str(cap_root.name),
                        ),
                        target_abs_path=Path("/dev/null"),
                        op="",
                        anchor="",
                        code="",
                        valid=False,
                        error=f"unknown injection point: {inject_id}",
                    )
                )
                continue
            pt = points[inject_id]
            parsed = _parse_position(pt.position)
            if not parsed:
                plans.append(
                    InjectionPlan(
                        point=pt,
                        extension=Extension(inject_at=inject_id, capability=cap_root.name),
                        target_abs_path=skeleton_root / pt.target,
                        op="",
                        anchor="",
                        code="",
                        valid=False,
                        error=f"invalid position format: {pt.position!r}",
                    )
                )
                continue
            op, anchor = parsed
            ext = Extension(
                inject_at=inject_id,
                code_template=raw.get("code_template", ""),
                inline_code=raw.get("inline_code", ""),
                capability=cap_root.name,
            )
            code = _load_template(cap_root, ext)
            plans.append(
                InjectionPlan(
                    point=pt,
                    extension=ext,
                    target_abs_path=skeleton_root / pt.target,
                    op=op,
                    anchor=anchor,
                    code=code,
                    valid=True,
                )
            )
    return plans


# ---------------------------------------------------------------------------
# 应用：仅支持 Python 源码定位（骨架现状）
# ---------------------------------------------------------------------------
_PY_DEF_RE_TPL = (
    r"^(?P<indent>[ \t]*)(async\s+def|def|class)\s+{name}\b[^\n]*:?\s*$"
)


def _locate_py_anchor(src: str, anchor: str):
    """First try strict def/class anchor; fallback to 'line-level generic anchor'.

    Generic anchor applies to plain call statements like ``app.include_router``, ``return foo()``;
    before/after means 'insert before/after that line'; replace means 'replace the entire line'.
    """
    pattern = re.compile(_PY_DEF_RE_TPL.format(name=re.escape(anchor)), re.MULTILINE)
    m = pattern.search(src)
    if m:
        return m, "block"
    # Fallback: capture the entire line containing the anchor
    loose = re.compile(
        r"^(?P<indent>[ \t]*)[^\n]*\b" + re.escape(anchor) + r"\b[^\n]*$",
        re.MULTILINE,
    )
    m2 = loose.search(src)
    if m2:
        return m2, "line"
    return None, None


def _apply_python(plan_item: InjectionPlan, src: str):
    """Execute a single injection on Python source; always returns ``(ApplyResult, new_src_or_none)``.

    Idempotency Protection
    ----------------------
    If ``plan_item.code`` already exists in the source (checked by ``# [<capability>]`` comment marker,
    or full snippet substring match), this injection is skipped and returns ``applied=False`` with
    ``error="already_injected"``, preventing duplicate inserts on repeated ``add-capability`` runs.
    """
    target = plan_item.target_abs_path
    # Idempotency check: use first comment line in inline_code (containing [cap-name]) as fingerprint.
    # Cannot solely rely on `# [{capability}]` because a single capability may have multiple
    # injection points (e.g., agent.before_push_text + agent.after_start) sharing the same
    # marker, which would cause the second injection to be falsely skipped.
    snippet_stripped = (plan_item.code or "").strip()
    fingerprint = next(
        (ln.strip() for ln in (plan_item.code or "").splitlines() if ln.strip()),
        "",
    )
    cap_marker_loose = f"# [{plan_item.extension.capability}]"
    already = False
    if snippet_stripped and snippet_stripped in src:
        already = True
    elif fingerprint and fingerprint in src:
        already = True
    elif cap_marker_loose in plan_item.code and snippet_stripped in src:
        already = True
    if already:
        return (
            ApplyResult(
                plan=plan_item, applied=False, dry_run=True,
                diff_preview=f"skip (already injected): {plan_item.extension.capability} -> {target.name}",
                error="already_injected",
            ),
            None,
        )
    m, kind = _locate_py_anchor(src, plan_item.anchor)
    if not m:
        return (
            ApplyResult(
                plan=plan_item, applied=False, dry_run=True,
                error=f"anchor '{plan_item.anchor}' not found in {target.name}",
            ),
            None,
        )
    indent = m.group("indent") or ""
    snippet = "\n".join(
        f"{indent}{line}" if line.strip() else line
        for line in plan_item.code.splitlines()
    )
    if kind == "block":
        if plan_item.op == "before":
            new_src = src[: m.start()] + snippet + "\n" + src[m.start():]
        elif plan_item.op == "after":
            rest = src[m.end():]
            end_in_rest = _find_block_end(rest, indent)
            end_pos = m.end() + end_in_rest
            new_src = src[:end_pos] + "\n" + snippet + "\n" + src[end_pos:]
        else:  # replace 整个 def/class 块
            rest = src[m.end():]
            end_in_rest = _find_block_end(rest, indent)
            end_pos = m.end() + end_in_rest
            new_src = src[: m.start()] + snippet + "\n" + src[end_pos:]
    else:  # 行级 anchor：before/after 在该行前/后插，replace 替换整行
        line_start = m.start()
        line_end = m.end()
        # 行级匹配未含尾随换行，定位到 \n 位置以保证拼接正确
        if line_end < len(src) and src[line_end] == "\n":
            line_end += 1
        if plan_item.op == "before":
            new_src = src[:line_start] + snippet + "\n" + src[line_start:]
        elif plan_item.op == "after":
            new_src = src[:line_end] + snippet + "\n" + src[line_end:]
        else:  # replace 整行
            new_src = src[:line_start] + snippet + "\n" + src[line_end:]
    diff = f"{plan_item.op}({kind}) {plan_item.anchor}\n{snippet[:200]}"
    return (
        ApplyResult(plan=plan_item, applied=True, dry_run=True, diff_preview=diff),
        new_src,
    )


def _find_block_end(rest: str, indent: str) -> int:
    """在函数体之后定位下一个同级/更低缩进的非空行起点。"""
    pos = 0
    for line in rest.splitlines(keepends=True):
        if line.strip() == "":
            pos += len(line)
            continue
        line_indent = len(line) - len(line.lstrip(" \t"))
        if line_indent <= len(indent) and line.strip():
            return pos
        pos += len(line)
    return len(rest)


def apply_plans(
    plans: List[InjectionPlan],
    *,
    dry_run: bool = True,
) -> List[ApplyResult]:
    """Execute injection plans. dry_run=True only produces diff previews without writing to disk."""
    results: List[ApplyResult] = []
    grouped: Dict[Path, List[InjectionPlan]] = {}
    for p in plans:
        if not p.valid:
            results.append(ApplyResult(plan=p, applied=False, dry_run=dry_run, error=p.error))
            continue
        grouped.setdefault(p.target_abs_path, []).append(p)

    for path, group in grouped.items():
        if not path.exists():
            for p in group:
                results.append(ApplyResult(
                    plan=p, applied=False, dry_run=dry_run,
                    error=f"target not found: {path}",
                ))
            continue
        # 仅支持 .py 文件原地注入；其他语言由 Agent 自行处理
        if path.suffix != ".py":
            for p in group:
                results.append(ApplyResult(
                    plan=p, applied=False, dry_run=dry_run,
                    diff_preview=f"non-python target {path.name}: hand off to adapter",
                ))
            continue
        current = path.read_text(encoding="utf-8")
        # 倒序处理，避免位置偏移
        sorted_group = sorted(group, key=lambda x: x.anchor)
        for p in sorted_group:
            res, new_src = _apply_python(p, current)
            if res.applied and new_src is not None:
                current = new_src
            res.dry_run = dry_run
            results.append(res)
        if not dry_run:
            path.write_text(current, encoding="utf-8")
    return results
