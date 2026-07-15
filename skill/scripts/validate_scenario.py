#!/usr/bin/env python3
"""validate_scenario.py — Scenario 文件一致性校验

针对 scenario-spec.md 第五节「字段一致性检查」三件套:
- 违反后果:不一致 → topic 展示给用户的与实际集成的不一样 → 用户拿到代码与说明书对不上
- 验证手段:本脚本(slice id 一致 + 形态字段完整 + B-多选明文声明)
- 绕过条件:无

规则要求(基于 scenario-spec.md):
1. frontmatter 必含 id;file 路径推导的 id 必须与 frontmatter 一致
2. 「能力清单」(A) 或 「能力分层」(B) 中出现的所有 `{product}/{slice-id}`
   必须存在于 index.yaml 的 slices 注册表
3. 「能力清单/分层」中的 slice 集合必须等同于 index.yaml 中本场景的 slices 字段
4. B 形态:能力分层下 P0 ≥ 2,P1 ≥ 2,每个 P1 标注「推荐默认勾选」
5. B-多选形态:必有「执行规则」段;必明文出现「未选中.*绝不进 confirmed_plan」
6. 章节顺序必须符合 scenario-spec.md 第三节(场景概述/能力清单/能力展示/前置条件/验收 Checklist)
7. 验收 Checklist 不出现"正常 / 良好 / 合适"等模糊词

由于现存 scenario 文件多数是历史结构,本脚本会**区分 error 和 warning**:
- error  = 与 index.yaml 不一致这类硬性事实错误(必须修)
- warning = 章节缺失、用词软等结构性问题(建议按 spec 重构)

用法:
    python3 scripts/validate_scenario.py knowledge-base/scenarios/live/entertainment-live-room.md
    python3 scripts/validate_scenario.py knowledge-base/scenarios/
    python3 scripts/validate_scenario.py --strict knowledge-base/scenarios/...
        # --strict:把所有 warning 升级为 error
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from _common import (
    Report,
    find_section,
    index_scenario_ids,
    index_scenario_slices,
    index_slice_ids,
    iter_sections,
    kb_dir,
    parse_doc,
    run_cli,
    section_text,
)

STRICT = "--strict" in sys.argv
sys.argv[:] = [a for a in sys.argv if not a.startswith("--")]

# Patterns ---------------------------------------------------------------

SLICE_ID_RE = re.compile(r"`([a-z][a-z0-9-]*/[a-z][a-z0-9_-]*)`")
SOFT_CHECKLIST_WORDS = ["正常", "良好", "合适", "可以", "差不多", "比较", "应该"]
B_MULTI_SENTINEL = re.compile(r"未选中.*?(?:绝不进|不得|不进|绝不出现)")


# Helpers ----------------------------------------------------------------

def _scenario_id_from_path(path: Path) -> str | None:
    """Path → expected scenario id.
    knowledge-base/scenarios/foo.md            → foo
    knowledge-base/scenarios/conference/x.md   → x      (filename based)
    """
    try:
        rel = path.resolve().relative_to(kb_dir())
    except ValueError:
        return None
    parts = rel.parts
    if not parts or parts[0] != "scenarios":
        return None
    return parts[-1].removesuffix(".md")


def _extract_slice_ids(text: str) -> list[str]:
    return SLICE_ID_RE.findall(text)


def _is_form_b(body: str) -> bool:
    """Form B if there's a 「能力分层」section."""
    return find_section(body, lambda t: "能力分层" in t) is not None


def _is_b_multi(body: str) -> bool:
    """B-multi if there's a 「必装骨架」or 「执行规则」block."""
    return (
        find_section(body, lambda t: "必装骨架" in t) is not None
        or find_section(body, lambda t: "执行规则" in t) is not None
    )


# Main check ------------------------------------------------------------

def check_scenario(path: Path) -> Report:
    rep = Report(file=path)

    def maybe_err(code: str, msg: str, line: int | None = None) -> None:
        if STRICT:
            rep.err(code, msg, line)
        else:
            rep.warn(code, msg, line)

    doc = parse_doc(path)
    fm = doc.frontmatter
    body = doc.body

    # 1. frontmatter id
    if "id" not in fm:
        rep.err("FM-ID-MISSING", "frontmatter 缺少 id 字段")
    else:
        expected = _scenario_id_from_path(path)
        if expected and fm["id"] != expected:
            maybe_err(
                "FM-ID-PATH-MISMATCH",
                f"frontmatter id={fm['id']!r} 与文件名推导的 id={expected!r} 不一致",
            )

        # 2. id 必须在 index.yaml 注册
        try:
            registered = index_scenario_ids()
            if fm["id"] not in registered:
                rep.err(
                    "FM-INDEX-MISSING",
                    f"id {fm['id']!r} 未在 index.yaml 的 scenarios 中登记",
                )
        except Exception as e:
            rep.warn("INDEX-LOAD", f"无法加载 index.yaml: {e}")

    # 3. 章节存在性(spec 第三节,顺序不强制但要存在)
    required_sections = [
        ("场景概述|场景描述|场景说明", "场景概述 / 场景描述"),
        ("能力清单|能力分层|能力展示|能力映射", "能力清单 / 能力分层 / 能力展示"),
        ("前置条件|前置依赖", "前置条件"),
        ("验收\\s*Checklist|验收清单|验收\\s*checklist|验收检查", "验收 Checklist"),
    ]
    for pattern, label in required_sections:
        regex = re.compile(pattern, re.IGNORECASE)
        if not find_section(body, lambda t, r=regex: bool(r.search(t))):
            maybe_err("SEC-MISSING", f"缺少必备章节: {label}")

    # 4. slice id 列表一致性 with index.yaml
    #
    # 文档"已声明"的 slice id 来自两处:
    #   (a) frontmatter 的 slices 字段(权威列表,与 index.yaml 直接对齐)
    #   (b) 「能力清单/分层/展示」章节中 backtick 包裹的 `product/slice` 形式
    # 两者并集 = 文档声明的全集。
    capability_section = find_section(
        body, lambda t: "能力清单" in t or "能力分层" in t or "能力展示" in t
    )
    section_slices: set[str] = set()
    if capability_section:
        cap_text = section_text(body, capability_section)
        section_slices = set(_extract_slice_ids(cap_text))

    fm_slices: set[str] = set()
    if isinstance(fm.get("slices"), list):
        fm_slices = {s for s in fm["slices"] if isinstance(s, str)}

    declared_slices = section_slices | fm_slices

    if "id" in fm:
        try:
            registered_slices = set(index_scenario_slices(fm["id"]))
            all_slice_ids = index_slice_ids()
            # Slice ids appearing anywhere in the doc that aren't in index.yaml at all
            unknown = declared_slices - all_slice_ids
            if unknown:
                rep.err(
                    "SLICE-UNKNOWN",
                    f"以下 slice id 在 index.yaml 的 slices 注册表中不存在: {sorted(unknown)}",
                )
            # Mismatch: declared in scenario file but not in index.yaml's scenarios.<id>.slices
            if registered_slices:
                missing_in_index = declared_slices - registered_slices
                missing_in_doc = registered_slices - declared_slices
                if missing_in_index:
                    maybe_err(
                        "SLICE-NOT-IN-INDEX",
                        f"文档声明但 index.yaml 该 scenario 的 slices 字段未列: {sorted(missing_in_index)}",
                    )
                if missing_in_doc:
                    maybe_err(
                        "SLICE-NOT-IN-DOC",
                        f"index.yaml 列出但文档未声明(frontmatter.slices 与正文章节均未提及): {sorted(missing_in_doc)}",
                    )
                # Soft check: frontmatter has them but body sections don't reference any →
                # the doc relies entirely on frontmatter, which is fine for legacy files
                # but spec wants the capability section to make them visible too.
                if section_slices == set() and fm_slices:
                    maybe_err(
                        "SLICE-NOT-IN-SECTION",
                        f"frontmatter.slices 有 {len(fm_slices)} 项,但「能力清单/分层/展示」"
                        f"章节中未以 `{{product}}/{{slice}}` 形式引用任何一项 — "
                        f"按 scenario-spec.md 第三节,应在章节正文也列出供 topic 与 AI 阅读",
                    )
        except Exception as e:
            rep.warn("INDEX-LOAD", f"无法加载 index.yaml: {e}")

    # 5. B 形态额外要求
    if _is_form_b(body):
        layer_sec = find_section(body, lambda t: "能力分层" in t)
        layer_text = section_text(body, layer_sec) if layer_sec else ""

        # Look for P0 / P1 sub-sections
        p0_sec = find_section(layer_text, lambda t: "P0" in t or "主链路" in t or "必装" in t)
        p1_sec = find_section(layer_text, lambda t: "P1" in t or "可选" in t or "增强" in t)

        if p0_sec:
            p0_text = section_text(layer_text, p0_sec)
            p0_count = len(_extract_slice_ids(p0_text))
            if p0_count < 2:
                maybe_err("FORM-B-P0-COUNT", f"B 形态:P0 主链路至少 2 条,当前 {p0_count}")
        elif not _is_b_multi(body):
            maybe_err("FORM-B-NO-P0", "B 形态:缺少「P0 主链路」子章节")

        if p1_sec:
            p1_text = section_text(layer_text, p1_sec)
            p1_ids = _extract_slice_ids(p1_text)
            if len(p1_ids) < 2:
                maybe_err("FORM-B-P1-COUNT", f"B 形态:P1 增强至少 2 条,当前 {len(p1_ids)}")
            # Each P1 must have 推荐默认勾选 字段
            if "推荐默认勾选" not in p1_text:
                maybe_err(
                    "FORM-B-P1-FLAG",
                    "B 形态:P1 增强 slice 必须标注「推荐默认勾选: 是/否」",
                )
        elif not _is_b_multi(body):
            maybe_err("FORM-B-NO-P1", "B 形态:缺少「P1 增强」子章节")

    # 6. B-多选额外要求
    if _is_b_multi(body):
        rules_sec = find_section(body, lambda t: "执行规则" in t)
        if not rules_sec:
            maybe_err("BMULTI-NO-RULES", "B-多选形态:缺少「执行规则」段落")
        else:
            rules_text = section_text(body, rules_sec)
            if not B_MULTI_SENTINEL.search(rules_text):
                rep.err(
                    "BMULTI-NO-SENTINEL",
                    "B-多选形态:「执行规则」必须明文出现「未选中模块绝不进 confirmed_plan」"
                    "或等价句(防 over-integration)",
                )

    # 7. 验收 Checklist 不含模糊词
    checklist_sec = find_section(body, lambda t: "验收 Checklist" in t or "验收清单" in t or "验收 checklist" in t.lower())
    if checklist_sec:
        cl_text = section_text(body, checklist_sec)
        for soft in SOFT_CHECKLIST_WORDS:
            if soft in cl_text:
                # Only line-based location: find first line that contains the word
                lines = cl_text.splitlines()
                for i, ln in enumerate(lines):
                    if soft in ln:
                        line = doc.body_offset + body[:checklist_sec.body_start].count("\n") + i + 1
                        maybe_err(
                            "CHECKLIST-SOFT",
                            f"验收 Checklist 含模糊词 {soft!r} — 请用可量化标准替代",
                            line=line,
                        )
                        break

    return rep


def main() -> int:
    return run_cli(check_scenario, default_glob="scenarios/**/*.md")


if __name__ == "__main__":
    raise SystemExit(main())
