#!/usr/bin/env python3
"""
generate.py — Phase 2 eval sheet generator (v2, cases.json v2.0).

从 cases.json v2 读 P2 case 生成：
  - testsheet.md          人读的题目单（多轮 case 每 turn 一段 prompt）
  - results_template.yaml 待填的答题卡（单轮扁平 / 多轮分 turns）

观察点由 cases.json 顶层的 obs_keys 字典驱动，new dimension 只需在 cases.json
加一条 obs_key + 引用即可，本脚本无需改动。

Usage:
    python3 generate.py
    python3 generate.py --tags smoke
    python3 generate.py --ide claude-code   # 预填 template 的 ide 字段
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


CATEGORY_ZH = {
    "faq":         "FAQ / 文档查询",
    "integration": "集成接入",
    "routing":     "路由判断",
    "guardrail":   "边界保护",
    "session":     "会话状态",
}


# ── 观察点抽取 ────────────────────────────────────────────────────────────────

def obs_keys_from_expect(expect: dict, obs_dict: dict) -> list[tuple[str, str, dict]]:
    """
    从一个 turn 的 expect 字段抽取需要观察的维度。
    每条 case 的 turn.expect 直接以 obs_key 为顶层键（如 route_level1: {...}），
    所以这里就是过滤那些真正声明了的 key。

    返回 [(obs_key, human_label, expect_detail), ...]
    """
    out = []
    for k, detail in expect.items():
        if k in obs_dict:
            label = obs_dict[k].get("label", k)
            out.append((k, label, detail))
    return out


def format_expect_hint(obs_key: str, detail) -> str:
    """把 expect 的 detail 字典渲染成一句给人看的具体期望。"""
    if not isinstance(detail, dict):
        return str(detail)

    parts = []
    if "target" in detail:
        parts.append(f"目标={detail['target']}")
    if "skill" in detail:
        parts.append(f"skill={detail['skill']}")
    if "must_not" in detail:
        parts.append(f"不该出现={' / '.join(detail['must_not'])}")
    if "topics" in detail:
        parts.append(f"追问=「{'、'.join(detail['topics'])}」")
    if "scripts" in detail:
        parts.append(f"脚本={' + '.join(detail['scripts'])}")
    if "required" in detail:
        parts.append(f"必须调用={' + '.join(detail['required'])}")
    if "any_of" in detail:
        parts.append(f"至少调用一个={' / '.join(detail['any_of'])}")
    if "hook" in detail:
        parts.append(f"hook={detail['hook']}")
    if "should_block" in detail:
        parts.append(f"应拦截={detail['should_block']}")
    if "status" in detail:
        parts.append(f"session.status={detail['status']}")
    if "product" in detail:
        parts.append(f"session.product={detail['product']}")
    if "platform" in detail:
        parts.append(f"session.platform={detail['platform']}")
    if "kind_should_be" in detail:
        parts.append(f"分类={detail['kind_should_be']}")
    if "deferred" in detail:
        parts.append("应推迟路由（先追问再路由）")
    if "resumed_from_guard" in detail:
        parts.append("应由 Session Guard 恢复")
    if "no_direct_code_gen" in detail:
        parts.append("不许直接吐代码")
    if "reason" in detail:
        parts.append(f"原因: {detail['reason']}")

    return "，".join(parts) if parts else json.dumps(detail, ensure_ascii=False)


# ── testsheet ────────────────────────────────────────────────────────────────

def build_testsheet(cases: list[dict], obs_dict: dict) -> str:
    lines = [
        "# TRTC Skill · Phase 2 手工测试单",
        "",
        "> **使用方式**",
        "> 1. 打开目标 IDE，新建空对话",
        "> 2. 逐条粘贴下方 Prompt，观察 skill 行为（多轮 case 顺序执行、共用同一对话）",
        "> 3. 对照「观察要点」填 `results.<ide>.yaml`（Y = 符合，N = 不符合，S = 跳过）",
        "> 4. 填完运行 `python3 score.py results.<ide>.yaml` 出报告",
        "",
        "---",
        "",
    ]

    for i, case in enumerate(cases, 1):
        cid = case["case_id"]
        cat = CATEGORY_ZH.get(case.get("category", ""), case.get("category", ""))
        tags = " · ".join(case.get("tags", []))
        turns = case.get("turns", [])
        desc = case.get("description", "")
        req_caps = case.get("ide_capabilities_required", [])
        case_expect = case.get("case_level_expect", {})

        header = f"## Case {i} · {cid}"
        if len(turns) > 1:
            header += f"    ⟳ {len(turns)} 轮"
        lines.append(header)
        lines.append("")
        lines.append(f"**类型**：{cat}　　**标签**：`{tags}`")
        if req_caps:
            lines.append(f"**IDE 能力要求**：{' + '.join(req_caps)}")
        lines.append("")
        if desc:
            lines.append(f"> {desc}")
            lines.append("")

        for t_idx, turn in enumerate(turns, 1):
            prompt = turn.get("user", "")
            expect = turn.get("expect", {})
            obs = obs_keys_from_expect(expect, obs_dict)

            turn_label = f"### Turn {t_idx}" if len(turns) > 1 else "### Prompt"
            lines.append(turn_label)
            lines.append("")
            lines.append("**Prompt（粘贴到 IDE）：**")
            lines.append("")
            lines.append("```")
            lines.append(prompt)
            lines.append("```")
            lines.append("")
            if obs:
                lines.append("**观察要点：**")
                lines.append("")
                for obs_key, label, detail in obs:
                    hint = format_expect_hint(obs_key, detail)
                    lines.append(f"- [ ] `{obs_key}` — {label}")
                    if hint:
                        lines.append(f"    - 期望：{hint}")
                lines.append("")

        if case_expect:
            lines.append("**Case 级期望（跨 turn）：**")
            for k, v in case_expect.items():
                lines.append(f"- [ ] `{k}` = {v}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ── results_template.yaml ────────────────────────────────────────────────────

def build_template(cases: list[dict], obs_dict: dict, ide: str = "") -> dict:
    tpl: dict = {
        "version": "2.0",
        "ide": ide or "<claude-code | cursor | codebuddy | codex>",
        "tester": "<填写测试人>",
        "date": "<YYYY-MM-DD>",
        "cases": [],
    }

    for case in cases:
        cid = case["case_id"]
        turns = case.get("turns", [])
        case_expect = case.get("case_level_expect", {})
        req_caps = case.get("ide_capabilities_required", [])

        entry: dict = {"case_id": cid}
        if req_caps:
            entry["ide_capabilities_required"] = req_caps

        # 单轮 → 扁平 observations；多轮 → turns 分组
        if len(turns) == 1:
            expect = turns[0].get("expect", {})
            obs = obs_keys_from_expect(expect, obs_dict)
            entry["observations"] = {k: "?" for k, _, _ in obs}
        else:
            entry["turns"] = []
            for t_idx, turn in enumerate(turns, 1):
                expect = turn.get("expect", {})
                obs = obs_keys_from_expect(expect, obs_dict)
                entry["turns"].append({
                    "turn": t_idx,
                    "observations": {k: "?" for k, _, _ in obs},
                })

        if case_expect:
            entry["case_level"] = {k: "?" for k in case_expect}

        entry["notes"] = ""
        tpl["cases"].append(entry)

    return tpl


# ── 极简 yaml writer（无依赖）────────────────────────────────────────────────

def _scalar(v) -> str:
    """把 python 标量转成 yaml 表示，为保留字符加引号避免 parser 歧义。"""
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None or v == "":
        return ""
    s = str(v)
    # yaml 里以 ? / - / : / # 等开头、或纯 ? 的值必须加引号
    if s in ("?", "!", "&", "*", "|", ">", "-") or s.startswith(("? ", "- ", ": ", "# ", "% ", "@ ", "` ")):
        return f'"{s}"'
    return s


def dict_to_yaml(d, indent: int = 0) -> str:
    lines = []
    pad = "  " * indent

    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, dict):
                if not v:
                    lines.append(f"{pad}{k}: {{}}")
                else:
                    lines.append(f"{pad}{k}:")
                    lines.append(dict_to_yaml(v, indent + 1))
            elif isinstance(v, list):
                if not v:
                    lines.append(f"{pad}{k}: []")
                else:
                    # scalar list → keep on one line as JSON (e.g. tags)
                    if all(not isinstance(x, (dict, list)) for x in v):
                        lines.append(f"{pad}{k}: {json.dumps(v, ensure_ascii=False)}")
                    else:
                        lines.append(f"{pad}{k}:")
                        for item in v:
                            if isinstance(item, dict):
                                first = True
                                for ik, iv in item.items():
                                    prefix = f"{pad}  - " if first else f"{pad}    "
                                    first = False
                                    if isinstance(iv, dict):
                                        if not iv:
                                            lines.append(f"{prefix}{ik}: {{}}")
                                        else:
                                            lines.append(f"{prefix}{ik}:")
                                            lines.append(dict_to_yaml(iv, indent + 3))
                                    elif isinstance(iv, list):
                                        # scalar list on same line, list-of-dict expanded
                                        if all(not isinstance(x, (dict, list)) for x in iv):
                                            lines.append(f"{prefix}{ik}: {json.dumps(iv, ensure_ascii=False)}")
                                        else:
                                            lines.append(f"{prefix}{ik}:")
                                            nested_pad = "  " * (indent + 2)
                                            for sub in iv:
                                                if isinstance(sub, dict):
                                                    sub_first = True
                                                    for sk, sv in sub.items():
                                                        sub_prefix = f"{nested_pad}- " if sub_first else f"{nested_pad}  "
                                                        sub_first = False
                                                        if isinstance(sv, dict):
                                                            if not sv:
                                                                lines.append(f"{sub_prefix}{sk}: {{}}")
                                                            else:
                                                                lines.append(f"{sub_prefix}{sk}:")
                                                                lines.append(dict_to_yaml(sv, indent + 4))
                                                        else:
                                                            lines.append(f"{sub_prefix}{sk}: {_scalar(sv)}")
                                                else:
                                                    lines.append(f"{nested_pad}- {_scalar(sub)}")
                                    else:
                                        lines.append(f"{prefix}{ik}: {_scalar(iv)}")
                            else:
                                lines.append(f"{pad}  - {_scalar(item)}")
            else:
                lines.append(f"{pad}{k}: {_scalar(v)}")

    return "\n".join(lines)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Phase 2 testsheet + results template")
    parser.add_argument("--cases", default=str(HERE / "cases.json"))
    parser.add_argument("--out-dir", default=str(HERE))
    parser.add_argument("--tags", help="Comma-separated tag filter, e.g. smoke")
    parser.add_argument("--ide", default="", help="Prefill ide field in template")
    args = parser.parse_args()

    cases_path = Path(args.cases)
    if not cases_path.exists():
        sys.exit(f"cases.json not found: {cases_path}")

    with open(cases_path) as f:
        data = json.load(f)

    if not data.get("version", "").startswith("2."):
        sys.exit(f"cases.json v{data.get('version', '?')} not supported (need v2.x)")

    obs_dict = data.get("obs_keys", {})
    if not obs_dict:
        sys.exit("cases.json missing obs_keys dictionary")

    tag_filter = set(args.tags.split(",")) if args.tags else set()
    p2_cases = [
        c for c in data["cases"]
        if c.get("phase") == "p2"
        and (not tag_filter or tag_filter.intersection(c.get("tags", [])))
    ]
    if not p2_cases:
        sys.exit("No P2 cases matched.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sheet_path = out_dir / "testsheet.md"
    sheet_path.write_text(build_testsheet(p2_cases, obs_dict), encoding="utf-8")
    print(f"✓  testsheet:          {sheet_path}")

    tpl = build_template(p2_cases, obs_dict, args.ide)
    tpl_path = out_dir / "results_template.yaml"
    tpl_path.write_text(dict_to_yaml(tpl) + "\n", encoding="utf-8")
    print(f"✓  results template:   {tpl_path}  ({len(p2_cases)} cases)")

    n_multi = sum(1 for c in p2_cases if len(c.get("turns", [])) > 1)
    print(f"   ├─ 单轮 case: {len(p2_cases) - n_multi}")
    print(f"   └─ 多轮 case: {n_multi}")
    print()
    print("下一步：")
    print(f"  1. 打开 testsheet.md，逐条在 IDE 里跑 prompt")
    print(f"  2. cp results_template.yaml results.<ide>.yaml，填 Y / N / S")
    print(f"  3. python3 score.py results.<ide>.yaml")


if __name__ == "__main__":
    main()
