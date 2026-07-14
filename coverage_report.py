#!/usr/bin/env python3
"""
coverage_report.py — 生成 corpus 评测覆盖报告（人话版）

从 eval-runs out-dir 聚合三个 orthogonal 信号：
  1. 触发正确性: 读 out-dir/results*.yaml（8 维度 Y/N）
  2. 能力覆盖: 复用 bucket_classifier 分析 transcripts/*.jsonl（bucket A/B/C/D/E?）
  3. 用例元数据: 从 cases.json 读 corpus_meta（product/intent/description）

呈现原则：顶部 TL;DR 给人看，技术细节 <details> 折叠给 AI 看。

Usage:
    python3 coverage_report.py --out-dir ./eval-runs/corpus-smoke-2026-07-14
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from bucket_classifier import classify_file, BucketVerdict  # noqa: E402


HARD_OBS = {
    "route_triggered", "reporting_called", "hooks_guarded",
    "session_state", "clarification_raised", "tools_called",
}
SOFT_OBS = {"route_level1", "route_level2"}

# bucket → (emoji, 短标签, 一句话解释)
BUCKET_META = {
    "A":  ("🟢", "覆盖完整",       "本地文档命中，或 docsbot + 本地双命中"),
    "B":  ("🟡", "只靠 docsbot",   "本地文档无覆盖，docsbot 挂就失守"),
    "C":  ("🟠", "拒答",           "skill 明说不支持 / 找不到"),
    "D":  ("🔵", "追问无路",       "反复追问最终没答上"),
    "E?": ("🚨", "疑似瞎编",       "有回答但没检索源，可能是幻觉"),
    "?":  ("❓", "未分类",         ""),
}


# ── data loaders ───────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_corpus_meta(cases_path: Path) -> dict[str, dict]:
    with open(cases_path, encoding="utf-8") as f:
        data = json.load(f)
    m = {}
    for c in data.get("cases", []):
        if not isinstance(c, dict) or "case_id" not in c:
            continue
        if "corpus" not in c.get("tags", []):
            continue
        meta = dict(c.get("corpus_meta", {}))
        meta["description"] = c.get("description", "")
        m[c["case_id"]] = meta
    return m


def _merge_results(out_dir: Path, ide: str) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for yf in sorted(out_dir.glob(f"results*{ide}.yaml")):
        data = _load_yaml(yf)
        for c in data.get("cases", []):
            cid = c.get("case_id")
            if cid:
                merged[cid] = c.get("observations", {})
    return merged


def _extract_case_id(transcript_name: str) -> str:
    m = re.match(r"^(.+?)\.turn\d+\.jsonl$", transcript_name)
    return m.group(1) if m else transcript_name.replace(".jsonl", "")


# ── correctness ─────────────────────────────────────────────────────────────

def _correctness(obs: dict) -> tuple[bool, list[str], list[str]]:
    """(pass, hard_fail_dims, soft_fail_dims)"""
    hard_fails, soft_fails = [], []
    for k, v in obs.items():
        if str(v).upper() != "N":
            continue
        (soft_fails if k in SOFT_OBS else hard_fails).append(k)
    return (not hard_fails, hard_fails, soft_fails)


# ── text helpers ────────────────────────────────────────────────────────────

def _topic(cid: str, meta: dict) -> str:
    """从 description 提取主题，去掉 'Corpus · Xxx FAQ ·' 前缀。
    'Corpus · Chat FAQ · Vue3 UIKit 消息列表头像配置' → 'Vue3 UIKit 消息列表头像配置'
    """
    desc = str(meta.get("description", "")).strip()
    if not desc:
        return cid
    parts = [p.strip() for p in desc.split("·")]
    return parts[-1] if len(parts) > 1 else desc


def _path_desc(sig) -> str:
    """人话数据源描述"""
    parts = []
    if sig.docsbot_could_answer is True:
        parts.append("docsbot")
    if sig.local_slice_read:
        parts.append(f"{len(sig.local_slice_read)} 份本地文档")
    if sig.webfetch_used:
        parts.append("webfetch 兜底")
    return " + ".join(parts) if parts else "(无检索源)"


def _speed_hint(sig) -> str:
    """直观耗时/消耗描述"""
    if sig.n_tool_calls >= 20 and sig.n_error_tool_results >= 3:
        return "🐢 慢（多次 fallback）"
    if sig.n_tool_calls <= 10:
        return "🚀 快"
    return "⚖️ 中等"


def _product_conclusion(cnt: dict[str, int]) -> str:
    total = sum(cnt.values())
    a, b, c, d, e = (cnt.get(x, 0) for x in ("A", "B", "C", "D", "E?"))
    if a == total:
        return "🟢 本地覆盖完整"
    if b >= 1 and a == 0:
        return "🟡 全部依赖 docsbot"
    if b >= 1:
        return "🟡 部分缺口"
    if c >= 1:
        return "🟠 有拒答"
    if d >= 1:
        return "🔵 追问无路"
    if e >= 1:
        return "🚨 疑似幻觉"
    return "-"


# ── main rendering ─────────────────────────────────────────────────────────

def render_report(
    corpus_meta: dict[str, dict],
    results: dict[str, dict],
    verdicts: dict[str, BucketVerdict],
    ide: str,
    out_dir: Path,
) -> str:
    case_ids = sorted(cid for cid in corpus_meta if cid in results or cid in verdicts)
    n = len(case_ids)
    n_measured = sum(1 for cid in case_ids if cid in results)
    n_pass = sum(1 for cid in case_ids if cid in results and _correctness(results[cid])[0])
    total_corpus = len(corpus_meta)

    gaps = [(cid, corpus_meta[cid], verdicts[cid])
            for cid in case_ids
            if cid in verdicts and verdicts[cid].bucket in ("B", "C", "D", "E?")]
    good = [(cid, corpus_meta[cid], verdicts[cid])
            for cid in case_ids
            if cid in verdicts and verdicts[cid].bucket == "A"]

    L: list[str] = []

    # ─── Header ────────────────────────────────────────────────
    L += [
        f"**IDE**: `{ide}`  ·  **日期**: {date.today().isoformat()}  ·  **out-dir**: `{out_dir.name}`  ·  **范围**: {n}/{total_corpus} 条 corpus seed",
        "",
    ]

    # ─── TL;DR ─────────────────────────────────────────────────
    L += ["## 📋 TL;DR", ""]

    if n_measured:
        line = f"- ✅ **触发正确性**: {n_pass}/{n_measured} 通过"
        if n_pass == n_measured:
            line += "（skill 都按预期触发）"
        else:
            line += f"（{n_measured - n_pass} 条有触发问题，见 Skill Eval Score Report 评论详情）"
        L.append(line)

    if gaps:
        L.append("")
        L.append(f"### ⚠️ 发现 {len(gaps)} 个能力暗雷")
        L.append("_触发都对了，但 AI 的回答有覆盖缺口_：")
        L.append("")
        for cid, meta, v in gaps:
            emoji, label, why = BUCKET_META.get(v.bucket, BUCKET_META["?"])
            L.append(
                f"- {emoji} **{meta.get('product', '?')}** · _{_topic(cid, meta)}_  \n"
                f"  → **{label}** — {why}"
            )

    if good:
        L.append("")
        L.append(f"### 🟢 {len(good)} 个覆盖完整")
        L.append("")
        for cid, meta, v in good:
            s = v.signals
            note = ""
            if s.local_slice_read:
                note = f"（读了 {len(s.local_slice_read)} 份本地文档）"
            L.append(f"- **{meta.get('product', '?')}** · _{_topic(cid, meta)}_ {note}")

    # 耗时/消耗对比 - 仅在多条 case 时展示
    if len([cid for cid in case_ids if cid in verdicts]) >= 2:
        L += ["", "### ⏱ 耗时/消耗对比", "",
              "_tool 数量 ≈ token 消耗；error 多说明可能有 fallback 循环_", ""]
        for cid in case_ids:
            v = verdicts.get(cid)
            if not v:
                continue
            s = v.signals
            prod = corpus_meta[cid].get("product", "?")
            L.append(
                f"- **{prod}**: {s.n_tool_calls} tools · {s.n_error_tool_results} errors · {_speed_hint(s)}"
            )

    L += ["", "---", ""]

    # ─── 技术细节 (folded) ─────────────────────────────────────
    L += [
        "<details>",
        "<summary><b>📊 技术细节</b>（点开看：8 维度触发观察点 · bucket 判定 · 每条数据源）</summary>",
        "",
        "### 触发正确性 — 每条 case",
        "",
        "| Case | Product | Intent | Pass | Fail / Concern |",
        "|---|---|---|:---:|---|",
    ]
    for cid in case_ids:
        meta = corpus_meta[cid]
        obs = results.get(cid)
        if obs is None:
            L.append(f"| {cid} | {meta.get('product', '?')} | {meta.get('intent', '?')} | — | (未跑) |")
            continue
        ok, hard, soft = _correctness(obs)
        mark = "✅" if ok else "❌"
        issues = []
        if hard:
            issues.append("⚠️ " + " ".join(hard))
        if soft:
            issues.append("· " + " ".join(soft))
        L.append(
            f"| {cid} | {meta.get('product', '?')} | {meta.get('intent', '?')} | {mark} | {' '.join(issues) or '-'} |"
        )

    L += [
        "",
        "### 能力覆盖 — 每条数据源",
        "",
        "| Case | Product | 结论 | 数据源 | Tools | Errors |",
        "|---|---|---|---|---:|---:|",
    ]
    for cid in case_ids:
        meta = corpus_meta[cid]
        v = verdicts.get(cid)
        if v is None:
            L.append(f"| {cid} | {meta.get('product', '?')} | — | — | — | — |")
            continue
        s = v.signals
        emoji, label, _ = BUCKET_META.get(v.bucket, BUCKET_META["?"])
        L.append(
            f"| {cid} | {meta.get('product', '?')} | {emoji} {label} | {_path_desc(s)} | "
            f"{s.n_tool_calls} | {s.n_error_tool_results} |"
        )

    # 按产品聚合
    by_product: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for cid in case_ids:
        v = verdicts.get(cid)
        if v is None:
            continue
        by_product[corpus_meta[cid].get("product", "?")][v.bucket] += 1

    if by_product:
        L += [
            "",
            "### 按产品聚合",
            "",
            "| Product | Cases | 🟢 | 🟡 | 🟠 | 🔵 | 🚨 | 结论 |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
        for prod in sorted(by_product):
            cnt = by_product[prod]
            total = sum(cnt.values())
            vals = [cnt.get(k, 0) for k in ("A", "B", "C", "D", "E?")]
            L.append(
                f"| {prod} | {total} | " + " | ".join(str(x) for x in vals) +
                f" | {_product_conclusion(cnt)} |"
            )

    L += ["", "</details>", ""]

    # ─── 术语说明 (folded) ─────────────────────────────────────
    L += [
        "<details>",
        "<summary><b>📖 术语说明</b>（点开看：这条报告 vs Skill Eval Score Report 的区别 · bucket 定义 · 观察点分级）</summary>",
        "",
        "**PR 上会出现两条评论，各答一个问题**：",
        "",
        "| 评论 | 回答的问题 |",
        "|---|---|",
        "| **Skill Eval Score Report** | skill/工具**有没有按预期触发**？（涵盖所有 P2 case，不只 corpus）|",
        "| **Corpus Coverage Report**（本条）| AI 的**回答质量**如何？能力有没有覆盖用户提问？|",
        "",
        "**Bucket（能力覆盖分类）**：",
        "",
        "| Bucket | 含义 | 说明 |",
        "|---|---|---|",
    ]
    for k in ("A", "B", "C", "D", "E?"):
        emoji, label, desc = BUCKET_META[k]
        L.append(f"| {emoji} `{k}` {label} | | {desc} |")

    L += [
        "",
        "**触发正确性观察点分级**（如果你看到 route_level1 fail 但整体 pass，就是这个原因）：",
        "- `route_triggered` = **critical** → 主 skill 未触发时整 case fail",
        "- `route_level1` / `route_level2` = **soft** → 路由准确度还没优化，N 只记 minor concern",
        "- 其他 hard 观察点 → 任一 N 都会拖 case fail",
        "",
        "</details>",
        "",
        "---",
        "",
        "**已知限制**：",
        f"- 本次覆盖 {n}/{total_corpus} 条 corpus seed",
        "- 🚨 疑似瞎编 需 LLM judge 二次确认，本工具不做",
        "",
    ]

    return "\n".join(L)


# ── main ───────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Corpus 评测覆盖报告生成器")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--ide", default="claude-code")
    ap.add_argument("--cases", default=str(HERE / "cases.json"))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    if not out_dir.exists():
        sys.exit(f"out-dir not found: {out_dir}")

    corpus_meta = _load_corpus_meta(Path(args.cases))
    if not corpus_meta:
        sys.exit(f"no corpus cases in {args.cases} (tag=corpus)")

    results = _merge_results(out_dir, args.ide)

    transcripts_dir = out_dir / "transcripts"
    verdicts: dict[str, BucketVerdict] = {}
    if transcripts_dir.exists():
        for jsonl in sorted(transcripts_dir.glob("*.jsonl")):
            cid = _extract_case_id(jsonl.name)
            try:
                verdicts[cid] = classify_file(jsonl, dialect="claude")
            except Exception as e:
                print(f"[warn] failed to classify {jsonl.name}: {e}", file=sys.stderr)

    md = render_report(corpus_meta, results, verdicts, args.ide, out_dir)
    report_path = out_dir / "report.md"
    report_path.write_text(md, encoding="utf-8")

    n_pass = sum(1 for cid, obs in results.items() if _correctness(obs)[0])
    buckets: dict[str, int] = defaultdict(int)
    for v in verdicts.values():
        buckets[v.bucket] += 1

    print(f"report → {report_path}")
    print(f"trigger correctness: {n_pass}/{len(results)} pass")
    print(f"bucket distribution: {dict(buckets)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
