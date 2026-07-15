#!/usr/bin/env python3
"""validate_frontmatter.py — slice 文件的 frontmatter 校验

针对 slice-spec.md 第四节的 frontmatter 三件套:
- 违反后果:字段缺失或与 index.yaml 不一致 → AI 路由到错误 slice
- 验证手段:本脚本(检查必填字段齐全 + 与 index.yaml 一致)
- 绕过条件:无

可处理两种 slice 类型:
1. 产品级概览 (`slices/{product}/{ability}.md`)
   必填:id / name / product / tags(≥3) / platforms
2. 平台实现文件 (`slices/{product}/{platform}/{ability}.md`)
   必填:id / platform / api_docs(≥1)

通过路径自动判断类型;不会误报。

用法:
    python3 scripts/validate_frontmatter.py knowledge-base/slices/live/coguest-apply.md
    python3 scripts/validate_frontmatter.py knowledge-base/slices/         # 整个目录
"""
from __future__ import annotations

from pathlib import Path

from _common import (
    Report,
    index_slice_ids,
    kb_dir,
    parse_doc,
    run_cli,
)

VALID_PLATFORMS = {"web", "android", "ios", "flutter", "electron", "unity"}

PRODUCT_LEVEL_REQUIRED = ["id", "name", "product", "tags", "platforms"]
PLATFORM_LEVEL_REQUIRED = ["id", "platform", "api_docs"]


def is_platform_file(path: Path) -> bool:
    """`slices/{product}/{platform}/{ability}.md` → True
       `slices/{product}/{ability}.md`              → False"""
    try:
        rel = path.resolve().relative_to(kb_dir())
    except ValueError:
        return False
    parts = rel.parts
    # parts[0] == 'slices', parts[1] == product
    if len(parts) < 3 or parts[0] != "slices":
        return False
    # platform file = depth 4 (slices/product/platform/ability.md)
    return len(parts) >= 4 and parts[2] in VALID_PLATFORMS


def expected_id_from_path(path: Path) -> str | None:
    """Build the canonical slice id from the file path.

    slices/live/coguest-apply.md       → live/coguest-apply
    slices/live/ios/coguest-apply.md   → live/coguest-apply (NOT live/ios/...)
    """
    try:
        rel = path.resolve().relative_to(kb_dir())
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) < 3 or parts[0] != "slices":
        return None
    product = parts[1]
    if is_platform_file(path):
        # parts: slices, product, platform, ability.md (or deeper)
        ability = parts[-1].removesuffix(".md")
    else:
        ability = parts[-1].removesuffix(".md")
    return f"{product}/{ability}"


def check_frontmatter(path: Path) -> Report:
    rep = Report(file=path)
    doc = parse_doc(path)
    fm = doc.frontmatter

    if not fm:
        rep.err("FM-MISSING", "frontmatter 缺失或为空")
        return rep

    is_platform = is_platform_file(path)
    required = PLATFORM_LEVEL_REQUIRED if is_platform else PRODUCT_LEVEL_REQUIRED

    # 1. required fields exist
    for field in required:
        if field not in fm:
            rep.err("FM-FIELD-MISSING", f"必填字段缺失: {field!r}")

    # 2. id format & path consistency
    expected_id = expected_id_from_path(path)
    if "id" in fm:
        if not isinstance(fm["id"], str):
            rep.err("FM-ID-TYPE", f"id 必须是字符串,got {type(fm['id']).__name__}")
        elif expected_id and fm["id"] != expected_id:
            rep.err(
                "FM-ID-PATH-MISMATCH",
                f"id={fm['id']!r} 与文件路径推导的 id={expected_id!r} 不一致",
            )

    # 3. tags ≥ 3 (product-level only)
    if not is_platform and "tags" in fm:
        tags = fm["tags"]
        if not isinstance(tags, list):
            rep.err("FM-TAGS-TYPE", f"tags 必须是数组,got {type(tags).__name__}")
        elif len(tags) < 3:
            rep.err("FM-TAGS-COUNT", f"tags 至少需要 3 个,got {len(tags)}")

    # 4. platforms list valid (product-level)
    if not is_platform and "platforms" in fm:
        plats = fm["platforms"]
        if not isinstance(plats, list) or not plats:
            rep.err("FM-PLATFORMS", f"platforms 必须是非空数组,got {plats!r}")
        else:
            unknown = [p for p in plats if p not in VALID_PLATFORMS]
            if unknown:
                rep.err(
                    "FM-PLATFORMS-UNKNOWN",
                    f"platforms 含未知值: {unknown!r};合法值: {sorted(VALID_PLATFORMS)}",
                )

    # 5. platform field valid (platform-level)
    if is_platform and "platform" in fm:
        if fm["platform"] not in VALID_PLATFORMS:
            rep.err(
                "FM-PLATFORM-UNKNOWN",
                f"platform={fm['platform']!r} 不是合法值;合法值: {sorted(VALID_PLATFORMS)}",
            )

    # 6. api_docs structure (platform-level)
    if is_platform and "api_docs" in fm:
        docs = fm["api_docs"]
        if not isinstance(docs, list) or not docs:
            rep.err("FM-API-DOCS", f"api_docs 必须是非空数组,got {docs!r}")
        else:
            for i, entry in enumerate(docs):
                if not isinstance(entry, dict):
                    rep.err("FM-API-DOCS-TYPE", f"api_docs[{i}] 必须是 mapping(含 title 与 url)")
                    continue
                if "title" not in entry or not entry.get("title"):
                    rep.err("FM-API-DOCS-TITLE", f"api_docs[{i}] 缺少 title 或为空")
                if "url" not in entry or not entry.get("url"):
                    rep.err("FM-API-DOCS-URL", f"api_docs[{i}] 缺少 url 或为空")
                else:
                    url = entry["url"]
                    if url in ("TODO", "todo", "TBD") or url.startswith("TODO"):
                        rep.err("FM-API-DOCS-TODO", f"api_docs[{i}].url 是 TODO 占位,请填真实链接")

    # 7. consistency with index.yaml (product-level only — platform files share the same id)
    if "id" in fm and isinstance(fm["id"], str):
        try:
            ids = index_slice_ids()
            if fm["id"] not in ids:
                # Tolerated for platform-level files that intentionally precede the
                # product-level index entry; warn instead of err.
                if is_platform:
                    rep.warn(
                        "FM-INDEX-MISSING",
                        f"id {fm['id']!r} 未在 index.yaml 的 slices 中登记(平台实现文件,可能由产品级 slice 待补)",
                    )
                else:
                    rep.err(
                        "FM-INDEX-MISSING",
                        f"id {fm['id']!r} 未在 index.yaml 的 slices 中登记",
                    )
        except Exception as e:  # pragma: no cover
            rep.warn("INDEX-LOAD", f"无法加载 index.yaml: {e}")

    return rep


def main() -> int:
    return run_cli(check_frontmatter)


if __name__ == "__main__":
    raise SystemExit(main())
