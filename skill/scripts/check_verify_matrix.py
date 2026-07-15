#!/usr/bin/env python3
"""check_verify_matrix.py — 「验证矩阵」表校验

针对 slice-spec.md「验证矩阵」三件套:
- 违反后果:验证矩阵不全 → AI/人工无法系统性自验 → 上线事故
- 验证手段:本脚本(4 个层级各 ≥1 行;每条 MUST/MUST NOT 都能在矩阵层级
                   1 或 2 找到对应行;至少 1 条层级 3、1 条层级 4)
- 绕过条件:无

规则要求:
1. 「## 验证矩阵」section 必须存在
2. 必须含一张 markdown 表格,表头形如:层级 | 检查项 | 验证手段 | 预期结果
3. 4 个层级各 ≥ 1 行:
   - 1. 编译级
   - 2. 静态规则级
   - 3. 运行时级
   - 4. 业务行为级
4. 每条「代码生成约束」MUST/MUST NOT 的 backtick 符号至少出现在 1 行
   (层级 1 或 2)的「检查项」或「验证手段」列里 — 即 MUST 与矩阵的对应关系

用法:
    python3 scripts/check_verify_matrix.py knowledge-base/slices/live/ios/coguest-apply.md
"""
from __future__ import annotations

import re
from pathlib import Path

from _common import (
    Report,
    find_section,
    parse_doc,
    run_cli,
    section_text,
)

LEVEL_PATTERNS = {
    1: re.compile(r"\b1\.?\s*编译级\b|\b1\.\s*compile\b", re.IGNORECASE),
    2: re.compile(r"\b2\.?\s*静态规则级\b|\b2\.\s*static\b", re.IGNORECASE),
    3: re.compile(r"\b3\.?\s*运行时级\b|\b3\.\s*runtime\b", re.IGNORECASE),
    4: re.compile(r"\b4\.?\s*业务行为级\b|\b4\.\s*behavior\b", re.IGNORECASE),
}

BACKTICK_RE = re.compile(r"`([^`\n]+)`")


def _find_table(text: str) -> list[str] | None:
    """Return the lines of the first markdown table found in text, or None."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "|" in line and i + 1 < len(lines) and re.match(r"^\s*\|?\s*[-: ]+\|", lines[i + 1]):
            # Found header + separator
            table = [line]
            j = i + 1
            # include separator
            table.append(lines[j])
            j += 1
            while j < len(lines) and "|" in lines[j]:
                table.append(lines[j])
                j += 1
            return table
    return None


def _row_cells(line: str) -> list[str]:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return cells


def _gather_must_symbols(body: str) -> set[str]:
    """Collect all backtick symbols that appear inside MUST/MUST NOT rule heads.

    These are the symbols that MUST be referenced in the verify matrix (level 1/2).
    We deliberately don't pull from Verify lines — Verify is what the matrix
    operationalises, so requiring matrix to ALSO mention it would be tautological.
    """
    constraints = find_section(body, lambda t: "代码生成约束" in t)
    if not constraints:
        return set()
    text = section_text(body, constraints)
    symbols: set[str] = set()
    # Match numbered rule heads: 1. **必须 ...** or 1. **不要 ...**
    for m in re.finditer(r"^\s*\d+\.\s+\*\*([^*]+)\*\*", text, flags=re.MULTILINE):
        head = m.group(1)
        for s in BACKTICK_RE.findall(head):
            # Trim noisy decoration; spec uses bare symbols mostly.
            symbols.add(s.strip())
    return symbols


def check_verify_matrix(path: Path) -> Report:
    rep = Report(file=path)
    doc = parse_doc(path)

    matrix = find_section(doc.body, lambda t: "验证矩阵" in t)
    if not matrix:
        # Only platform-level files require a matrix; product-level can skip.
        # Heuristic: if 「代码生成约束」exists but 「验证矩阵」doesn't → fail.
        if find_section(doc.body, lambda t: "代码生成约束" in t):
            rep.err("MATRIX-MISSING", "存在「代码生成约束」但缺少「验证矩阵」section")
        return rep

    matrix_text = section_text(doc.body, matrix)
    matrix_offset = doc.body_offset + doc.body[:matrix.body_start].count("\n")

    table = _find_table(matrix_text)
    if not table:
        rep.err(
            "MATRIX-NO-TABLE",
            "「验证矩阵」section 中找不到 markdown 表格",
            line=matrix_offset,
        )
        return rep

    if len(table) < 3:  # header + sep + ≥1 row
        rep.err("MATRIX-EMPTY", f"验证矩阵表为空(只有 {len(table)} 行)", line=matrix_offset)
        return rep

    header_cells = _row_cells(table[0])
    if len(header_cells) < 4:
        rep.err(
            "MATRIX-COLUMNS",
            f"验证矩阵表至少需要 4 列(层级 / 检查项 / 验证手段 / 预期结果),got {len(header_cells)} 列",
            line=matrix_offset,
        )
        return rep

    rows = table[2:]  # skip header + separator

    # Count rows per level
    by_level: dict[int, list[list[str]]] = {1: [], 2: [], 3: [], 4: []}
    for row in rows:
        cells = _row_cells(row)
        if not cells:
            continue
        level_cell = cells[0]
        for level, pat in LEVEL_PATTERNS.items():
            if pat.search(level_cell):
                by_level[level].append(cells)
                break

    for level in (1, 2, 3, 4):
        if not by_level[level]:
            rep.err(
                "MATRIX-LEVEL-MISSING",
                f"层级 {level} 至少需要 1 行,当前 0 行",
                line=matrix_offset,
            )

    # Cross-check: each MUST/MUST NOT backtick symbol should appear somewhere
    # in level-1 or level-2 rows (检查项 or 验证手段 columns).
    must_symbols = _gather_must_symbols(doc.body)
    if must_symbols:
        haystack_level_12 = "\n".join(
            "|".join(cells) for level in (1, 2) for cells in by_level[level]
        )
        missing = []
        for sym in must_symbols:
            if sym not in haystack_level_12:
                missing.append(sym)
        if missing:
            # report up to first 5 to avoid spam
            shown = ", ".join(repr(s) for s in missing[:5])
            more = f"... (+{len(missing) - 5} more)" if len(missing) > 5 else ""
            rep.err(
                "MATRIX-MUST-MISSING",
                f"以下 MUST/MUST NOT 符号未出现在层级 1 或 2 的检查行中: {shown}{more}",
                line=matrix_offset,
            )

    return rep


def main() -> int:
    return run_cli(check_verify_matrix)


if __name__ == "__main__":
    raise SystemExit(main())
