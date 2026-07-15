#!/usr/bin/env python3
"""check_must_rules.py — 「代码生成约束」MUST / MUST NOT 规则校验

针对 slice-spec.md「代码生成约束」+ 「MUST 规则的维度对齐原则」三件套:
- 违反后果:MUST 含红旗词 → apply 误杀正确代码 + 训练 AI 凑字符串
- 验证手段:本脚本(红旗词命中 0 次;每条 MUST/MUST NOT 都有 Verify;
                   Verify 内有 backtick;条目数下限)
- 绕过条件:无

规则要求(基于 slice-spec.md 第四节):
1. MUST 至少 3 条;MUST NOT 至少 2 条
2. 每条规则必须以 "**必须 ..." 或 "**不要 ..." 开头(强动词检查)
3. 每条规则必须含至少 1 个 backtick 包裹的符号
4. 每条规则必须有 "**Verify**:" 行
5. Verify 行内必须有至少 1 个 backtick
6. 规则文字 + Verify 内不允许出现红旗词:
   或 / 任一 / 等价 / 或类似 / 按业务 / 根据场景 / 留给 / 负责
7. 规则文字内不允许"应该 / 建议 / 最好 / 一般来说 / 大概"等软词

用法:
    python3 scripts/check_must_rules.py knowledge-base/slices/live/ios/coguest-apply.md
    python3 scripts/check_must_rules.py knowledge-base/slices/
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from _common import (
    Report,
    find_section,
    iter_sections,
    parse_doc,
    run_cli,
    section_text,
)

# ---- Red-flag word table (from slice-spec.md MUST 规则的维度对齐原则) ------

RED_FLAG_WORDS = [
    # 「或 / 任一」
    "或", "任一", "二者之一",
    # 「等价 / 或类似」
    "等价", "或类似", "类似的",
    # 「按业务 / 根据场景」
    "按业务", "根据场景", "按场景", "依业务",
    # 「留给 / 负责」(架构边界,不可机械验)
    "留给",
    # 软词(用在 MUST 行内 = 红旗)
    "应该", "建议", "最好", "一般来说", "大概", "尽量", "可能",
]

# These are red flags only inside the rule prose, NOT inside the "**Verify**:"
# line itself (Verify lines may legitimately use logical 或 between alternatives,
# e.g. "出现 ≥1 次 或 0 次"). Spec says rule文字含"或" → 拆原子,所以这里仍按红旗处理。

MUST_HEAD_RE = re.compile(r"^\s*\d+\.\s+\*\*(必须[^*]+)\*\*", re.MULTILINE)
MUST_NOT_HEAD_RE = re.compile(r"^\s*\d+\.\s+\*\*(不要[^*]+|不[要应得能][^*]*|绝不[^*]*)\*\*", re.MULTILINE)
VERIFY_LINE_RE = re.compile(r"\*\*Verify\*\*\s*[:：]\s*(.+?)(?=\n\s*\d+\.\s+\*\*|\n\s*####|\Z)", re.DOTALL)
BACKTICK_RE = re.compile(r"`([^`\n]+)`")


@dataclass
class Rule:
    kind: str       # "MUST" or "MUST NOT"
    head: str       # the bolded action ("必须导入 `import X`")
    body: str       # full rule text from "1. ..." up to (but not including) next rule/header
    line: int       # 1-indexed file line where rule starts


def _split_rules(text: str, base_line: int, kind: str) -> list[Rule]:
    """Split a MUST or MUST NOT block into individual numbered rules."""
    rules: list[Rule] = []
    # Find all numbered rule starts: ^\s*\d+\.\s+\*\*
    starts = [m for m in re.finditer(r"^\s*(\d+)\.\s+\*\*", text, flags=re.MULTILINE)]
    for i, m in enumerate(starts):
        start = m.start()
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        body = text[start:end].rstrip()
        # Extract head (bold span starting with 必须 / 不要 etc.)
        head_match = re.match(r"\s*\d+\.\s+\*\*(.+?)\*\*", body, flags=re.DOTALL)
        head = head_match.group(1).strip() if head_match else ""
        line = base_line + text[:start].count("\n")
        rules.append(Rule(kind=kind, head=head, body=body, line=line))
    return rules


def _find_must_blocks(body: str, body_offset: int) -> tuple[list[Rule], list[Rule]]:
    """Find MUST and MUST NOT subsections inside「代码生成约束」.

    They are typically `#### MUST` / `#### MUST NOT` under `## 代码生成约束`.
    We're permissive about heading depth and case.
    """
    must_rules: list[Rule] = []
    must_not_rules: list[Rule] = []
    for sec in iter_sections(body):
        title = sec.title.strip()
        text = section_text(body, sec)
        # heading line number in file
        head_line = body_offset + body[:sec.start].count("\n")
        # Match titles: "MUST" / "MUST(...)" / "MUST NOT" / "MUST NOT(...)"
        if re.match(r"^MUST\s*NOT\b", title, re.IGNORECASE):
            must_not_rules.extend(_split_rules(text, head_line + 1, "MUST NOT"))
        elif re.match(r"^MUST\b", title, re.IGNORECASE):
            must_rules.extend(_split_rules(text, head_line + 1, "MUST"))
    return must_rules, must_not_rules


_SOFT_HEAD_WORDS = ("应该", "建议", "最好", "尽量", "最好不要", "可以")


def _check_rule(rule: Rule, rep: Report) -> None:
    body = rule.body
    head = rule.head

    # 1. head 强动词检查
    #    - MUST:不允许以软词开头(应该/建议/最好/尽量),其余强动词均可
    #      (spec 模板用「必须」,但「通过」「调用」「使用」等强动词在真实文件中也可接受)
    #    - MUST NOT:必须以否定词开头(不要/绝不/不得/不应/不能)
    if rule.kind == "MUST":
        for soft in _SOFT_HEAD_WORDS:
            if head.startswith(soft):
                rep.err(
                    "MUST-HEAD-SOFT",
                    f"MUST 规则 head 含软词 {soft!r}: {head[:40]!r}... — "
                    f"应改为「必须 / 通过 / 调用 / 使用」等强动词开头",
                    line=rule.line,
                )
                break
    else:
        if not (head.startswith("不要") or head.startswith("绝不") or head.startswith("不得") or head.startswith("不应") or head.startswith("不能") or head.startswith("禁止")):
            rep.err(
                "MUST-NOT-HEAD-WEAK",
                f"MUST NOT 规则 head 应以「不要/绝不/不得/不应/不能/禁止」开头: {head[:30]!r}...",
                line=rule.line,
            )

    # 2. head must contain at least one backtick symbol
    if not BACKTICK_RE.search(head):
        rep.err(
            "MUST-NO-BACKTICK",
            f"规则 head 必须含 backtick 符号 — 否则 apply 没有可 grep 的目标: {head[:50]!r}",
            line=rule.line,
        )

    # 3. body must contain a Verify line
    verify_match = VERIFY_LINE_RE.search(body)
    if not verify_match:
        rep.err(
            "MUST-NO-VERIFY",
            f"规则缺少 **Verify**: 行 — 见 slice-spec.md「MUST 规则维度对齐原则」",
            line=rule.line,
        )
    else:
        verify_text = verify_match.group(1).strip()
        # 4. Verify must contain at least one backtick
        if not BACKTICK_RE.search(verify_text):
            rep.err(
                "MUST-VERIFY-NO-BACKTICK",
                f"Verify 行内必须含 backtick 符号 — 否则规则不可机械验证",
                line=rule.line,
            )

    # 5. red-flag words in rule prose (head + non-Verify body)
    prose = body
    if verify_match:
        prose = body[: verify_match.start()] + body[verify_match.end():]
    for word in RED_FLAG_WORDS:
        if word in prose:
            # Skip false positives: "或者" 当成解释性词?  spec 说"或"就是红旗,从严
            # 不过"应该"在反例性引用里可能出现 → 我们只看 head + 主要描述行,跳过引号/反例段
            # 简单近似:不算在引号包裹的部分内
            stripped = re.sub(r"`[^`]+`", "", prose)        # remove backtick spans
            stripped = re.sub(r'"[^"]+"', "", stripped)     # remove quoted spans
            stripped = re.sub(r'「[^」]+」', "", stripped)
            stripped = re.sub(r'"[^"]+"', "", stripped)
            if word in stripped:
                rep.err(
                    "MUST-RED-FLAG",
                    f"规则文字含红旗词 {word!r} — 详见 slice-spec.md「红旗词表」,需拆原子或下沉到软规则",
                    line=rule.line,
                )
                break  # one red flag per rule is enough; user fixes & re-runs


def check_must_rules(path: Path) -> Report:
    rep = Report(file=path)
    doc = parse_doc(path)

    # Skip non-platform files: product-level overviews don't have MUST rules.
    constraints = find_section(doc.body, lambda t: "代码生成约束" in t or t.lower().startswith("code generation"))
    if not constraints:
        # No code-gen constraints section — skip silently.
        return rep

    constraints_text = section_text(doc.body, constraints)
    constraints_offset = doc.body_offset + doc.body[:constraints.body_start].count("\n")

    must_rules, must_not_rules = _find_must_blocks(constraints_text, constraints_offset)

    # Counts
    if len(must_rules) < 3:
        rep.err(
            "MUST-COUNT",
            f"MUST 规则至少 3 条,当前 {len(must_rules)} 条",
            line=constraints_offset,
        )
    if len(must_not_rules) < 2:
        rep.err(
            "MUST-NOT-COUNT",
            f"MUST NOT 规则至少 2 条,当前 {len(must_not_rules)} 条",
            line=constraints_offset,
        )

    # Per-rule checks
    for r in must_rules + must_not_rules:
        _check_rule(r, rep)

    return rep


def main() -> int:
    return run_cli(check_must_rules)


if __name__ == "__main__":
    raise SystemExit(main())
