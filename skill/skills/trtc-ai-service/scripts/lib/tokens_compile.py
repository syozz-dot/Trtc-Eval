"""tokens_compile —— compile design_tokens.json into CSS variable files.

Design goals:
- Single source of truth: design_tokens.json
- Compiled output: scenarios/**/ui/**/tokens.css (DESIGN_GUIDELINES §9 declares these must not be hand-edited)
- Naming aligns with DESIGN_GUIDELINES.md §2.1 CSS variable names (compact, not full flatten)
- No third-party dependencies (no style-dictionary, etc.)

Invocation:
    python3 -m scripts.lib.tokens_compile \\
        --src design_tokens.json \\
        --dest scenarios/customer-service/ui/widget-floating/tokens.css \\
        --dest scenarios/customer-service/ui/admin-board/tokens.css
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


_HEADER = (
    "/*\n"
    " * Auto-generated from design_tokens.json —— **DO NOT EDIT**\n"
    " * Build command: python3 -m scripts.lib.tokens_compile\n"
    " * Naming convention: see scenarios/customer-service/ui/design-system/DESIGN_GUIDELINES.md §2.1\n"
    " */\n"
)


# ---------------------------------------------------------------------------
# 命名映射：(json 路径) → (CSS 变量名)
# 注：与 DESIGN_GUIDELINES.md §2.1 完全对齐
# ---------------------------------------------------------------------------
_MAP: List[Tuple[str, str]] = [
    # color.background.*  → --color-bg-*
    ("color.background.gradient-start", "--color-bg-gradient-start"),
    ("color.background.gradient-end", "--color-bg-gradient-end"),
    ("color.background.gradient", "--color-bg-gradient"),
    ("color.background.surface", "--color-bg-surface"),
    ("color.background.surface-strong", "--color-bg-surface-strong"),
    ("color.background.border", "--color-bg-border"),
    # color.brand.*       → --color-brand-*
    ("color.brand.accent", "--color-brand-accent"),
    # color.text.*        → --color-text-*
    ("color.text.primary", "--color-text-primary"),
    ("color.text.secondary", "--color-text-secondary"),
    ("color.text.tertiary", "--color-text-tertiary"),
    ("color.text.disabled", "--color-text-disabled"),
    ("color.text.placeholder", "--color-text-placeholder"),
    # color.status.*      → --color-status-*
    ("color.status.success", "--color-status-success"),
    ("color.status.info", "--color-status-info"),
    ("color.status.warning", "--color-status-warning"),
    ("color.status.error", "--color-status-error"),
    # color.input.*       → --color-input-*
    ("color.input.background", "--color-input-bg"),
    ("color.input.icon-send", "--color-input-icon-send"),
    # typography.*        → --font-family-* / --font-size-* / --font-weight-* / --line-height-*
    ("typography.fontFamily.base", "--font-family-base"),
    ("typography.title.fontSize", "--font-size-title"),
    ("typography.title.fontWeight", "--font-weight-title"),
    ("typography.title.lineHeight", "--line-height-title"),
    ("typography.brandName.fontSize", "--font-size-brand"),
    ("typography.brandName.fontWeight", "--font-weight-brand"),
    ("typography.placeholder.fontSize", "--font-size-placeholder"),
    ("typography.placeholder.fontWeight", "--font-weight-placeholder"),
    # spacing.*           → --space-*
    ("spacing.card-padding", "--space-card-padding"),
    ("spacing.input-padding-x", "--space-input-padding-x"),
    ("spacing.input-padding-y", "--space-input-padding-y"),
    ("spacing.gap-brand-title", "--space-gap-brand-title"),
    # radius.*            → --radius-*
    ("radius.card", "--radius-card"),
    ("radius.input", "--radius-input"),
    ("radius.logo", "--radius-logo"),
]


# ---------------------------------------------------------------------------
# 视觉分组（输出顺序 + 注释分隔）
# ---------------------------------------------------------------------------
_GROUPS: List[Tuple[str, List[str]]] = [
    ("Background / surfaces", [
        "--color-bg-gradient-start", "--color-bg-gradient-end", "--color-bg-gradient",
        "--color-bg-surface", "--color-bg-surface-strong", "--color-bg-border",
    ]),
    ("Brand / accent", ["--color-brand-accent"]),
    ("Text", [
        "--color-text-primary", "--color-text-secondary", "--color-text-tertiary",
        "--color-text-disabled", "--color-text-placeholder",
    ]),
    ("Status (success / info / warning / error)", [
        "--color-status-success", "--color-status-info",
        "--color-status-warning", "--color-status-error",
    ]),
    ("Input", ["--color-input-bg", "--color-input-icon-send"]),
    ("Typography", [
        "--font-family-base",
        "--font-size-title", "--font-weight-title", "--line-height-title",
        "--font-size-brand", "--font-weight-brand",
        "--font-size-placeholder", "--font-weight-placeholder",
    ]),
    ("Spacing", [
        "--space-card-padding", "--space-input-padding-x",
        "--space-input-padding-y", "--space-gap-brand-title",
    ]),
    ("Radius", ["--radius-card", "--radius-input", "--radius-logo"]),
    ("Effects", ["--effect-input-blur"]),
]


def _walk_json(tokens: Dict[str, Any], path: str) -> Any:
    """按 'a.b.c' 路径取出 token 节点；返回 None 表示找不到。"""
    cur: Any = tokens
    for seg in path.split("."):
        if not isinstance(cur, dict) or seg not in cur:
            return None
        cur = cur[seg]
    return cur


def _format_value(node: Dict[str, Any]) -> str:
    """把 token 叶子节点转成 CSS 值字面量。"""
    val = node.get("value")
    typ = node.get("type")
    if typ == "blur" and isinstance(val, dict) and "radius" in val:
        return f"blur({val['radius']})"
    return str(val)


def compile_tokens(src: Path) -> str:
    raw = json.loads(src.read_text(encoding="utf-8"))

    # 第一遍：把 _MAP 中每个 token 的最终 CSS 值算出来
    resolved: Dict[str, str] = {}
    missing: List[str] = []
    for json_path, css_name in _MAP:
        node = _walk_json(raw, json_path)
        if not isinstance(node, dict) or "value" not in node:
            missing.append(json_path)
            continue
        resolved[css_name] = _format_value(node)

    # 单独补 effect.input-blur（_format_value 已能处理 dict→blur(...) ）
    eff_node = _walk_json(raw, "effect.input-blur")
    if isinstance(eff_node, dict):
        resolved["--effect-input-blur"] = _format_value(eff_node)

    if missing:
        raise SystemExit(
            "design_tokens.json is missing the following tokens. Please add them and re-run:\n  - "
            + "\n  - ".join(missing)
        )

    # 第二遍：按 _GROUPS 顺序输出
    lines = [_HEADER, ":root {"]
    first = True
    for group_label, names in _GROUPS:
        if not first:
            lines.append("")
        first = False
        lines.append(f"  /* {group_label} */")
        for n in names:
            v = resolved.get(n)
            if v is None:
                continue
            lines.append(f"  {n}: {v};")
    lines.append("}")
    lines.append("")  # 末尾换行
    return "\n".join(lines)


def _argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="design_tokens.json → CSS 变量")
    p.add_argument("--src", default="design_tokens.json")
    p.add_argument(
        "--dest",
        action="append",
        required=True,
        help="可重复，每次写一份产物",
    )
    return p


def main() -> int:
    args = _argparser().parse_args()
    src = Path(args.src)
    if not src.exists():
        print(f"src not found: {src}", file=sys.stderr)
        return 2
    css = compile_tokens(src)
    for dest_str in args.dest:
        dest = Path(dest_str)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(css, encoding="utf-8")
        print(f"wrote {dest} ({len(css)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
