#!/usr/bin/env python3
"""
coverage_report.py — 生成 corpus 评测覆盖报告（pipeline 最后一环）

从 eval-runs out-dir 聚合三个 orthogonal 信号：
  1. 触发正确性: 读 out-dir/results*.yaml（8 维度 Y/N，来自 run_eval.py）
  2. 能力覆盖: 复用 bucket_classifier 分析 out-dir/transcripts/*.jsonl（A/B/C/D/E?）
  3. 用例元数据: 从 cases.json 读 corpus_meta（product/intent）

输出 out-dir/report.md 并在 stdout 打摘要。
只报告 tag=corpus 的 case；其他 P1/P2 手写 case 不进此报告。

Usage:
    python3 coverage_report.py --out-dir ./eval-runs/corpus-smoke-2026-07-14
    python3 coverage_report.py --out-dir ./eval-runs/xxx --cases ./cases.json --ide claude-code
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


# ── data loaders ───────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_corpus_meta(cases_path: Path) -> dict[str, dict]:
    """从 cases.json 载入 case_id → {corpus_meta + description} 映射（只含 tag=corpus）"""
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
    """glob 所有 results*<ide>.yaml 合并 case_id → observations"""
    merged: dict[str, dict] = {}
    for yf in sorted(out_dir.glob(f"results*{ide}.yaml")):
        data = _load_yaml(yf)
        for c in data.get("cases", []):
            cid = c.get("case_id")
            if cid:
                merged[cid] = c.get("observations", {})
    return merged


def _extract_case_id(transcript_name: str) -> str:
    """P2-CORPUS-CHAT-001.turn1.jsonl → P2-CORPUS-CHAT-001"""
    m = re.match(r"^(.+?)\.turn\d+\.jsonl$", transcript_name)
    return m.group(1) if m else transcript_name.replace(".jsonl", "")


# ── correctness classification ─────────────────────────────────────────────

def _correctness(obs: dict) -> tuple[bool, list[str], list[str]]:
    """返回 (hard_pass, hard_fail_dims, soft_fail_dims)"""
    hard_fails, soft_fails = [], []
    for k, v in obs.items():
        val = str(v).upper()
        if val != "N":
            continue
        if k in SOFT_OBS:
            soft_fails.append(k)
        else:  # HARD_OBS 或未识别的都当 hard
            hard_fails.append(k)
    return (not hard_fails, hard_fails, soft_fails)


# ── rendering ───────────────────────────────────────────────────────────────

def _docsbot_mark(sig) -> str:
    if not sig.docsbot_called:
        return "-"
    if sig.docsbot_could_answer is True:
        return "✅"
    if sig.docsbot_could_answer is False:
        return "❌"
    return "?"


def _path_desc(v: BucketVerdict) -> str:
    s = v.signals
    parts = []
    if s.docsbot_could_answer is True:
        parts.append("docsbot")
    if s.local_slice_read:
        parts.append(f"{len(s.local_slice_read)} slice")
    if s.webfetch_used:
        parts.append("webfetch")
    return " + ".join(parts) if parts else "(no source)"


def _product_conclusion(cnt: dict[str, int], total: int) -> str:
    a, b, c, d, e = (cnt.get(x, 0) for x in ("A", "B", "C", "D", "E?"))
    if a == total:
        return "本地 KB 完整覆盖"
    if b >= 1 and a == 0:
        return "⚠️ 全部依赖 docsbot（本地 KB 缺）"
    if b >= 1:
        return "⚠️ 部分本地 KB 缺口"
    if c >= 1:
        return "❌ 显式拒答（有覆盖盲区）"
    if d >= 1:
        return "⚠️ 追问后无路"
    if e >= 1:
        return "🚨 疑似幻觉，需 LLM judge"
    return "-"


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
    n_bucketed = sum(1 for cid in case_ids if cid in verdicts)
    total_corpus = len(corpus_meta)

    L: list[str] = []
    L += [
        "# TRTC Skill · Corpus 评测覆盖报告",
        "",
        f"**IDE**: {ide}  ·  **日期**: {date.today().isoformat()}  ·  **out-dir**: `{out_dir.name}`",
        "",
        f"**范围**: {n} / {total_corpus} 条 corpus seed 已跑 · 触发正确性覆盖 {n_measured} · bucket 覆盖 {n_bucketed}",
        "",
        "本报告聚合两个 orthogonal 信号：",
        "1. **触发正确性**（skill/工具按预期触发）— 通过 8 维度 Y/N 判定",
        "2. **能力覆盖**（回答有没有实质内容 + 数据源）— 通过 bucket A/B/C/D/E? 判定",
        "",
        "触发正确性 pass 但 bucket ∈ {B/C/D/E?} 是**核心缺口信号** —— 路由/工具都对，但能力有暗雷。",
        "",
        "---",
        "",
        "## 1. 触发正确性",
        "",
        f"**Pass rate**: {n_pass}/{n_measured} = {100*n_pass/max(n_measured,1):.1f}%",
        "",
        "| Case | Product | Intent | Pass | Fail / Concern |",
        "|---|---|---|---|---|",
    ]
    for cid in case_ids:
        meta = corpus_meta[cid]
        obs = results.get(cid)
        if obs is None:
            L.append(f"| {cid} | {meta.get('product','?')} | {meta.get('intent','?')} | — | (未跑) |")
            continue
        ok, hard, soft = _correctness(obs)
        mark = "✅" if ok else "❌"
        issues = []
        if hard:
            issues.append("⚠️ " + " ".join(hard))
        if soft:
            issues.append("· " + " ".join(soft))
        L.append(
            f"| {cid} | {meta.get('product','?')} | {meta.get('intent','?')} | {mark} | {' '.join(issues) or '-'} |"
        )

    L += [
        "",
        "> `route_level1/2` 是 soft observation：N 只记 minor concern，不拖 case 到 fail。其他 hard 观察点任一 N 都会拖 fail。",
        "",
        "---",
        "",
        "## 2. 能力覆盖 · Bucket 分布",
        "",
        "| Case | Product | Bucket | Path (数据源) | Tools | Errors | 说明 |",
        "|---|---|:---:|---|---:|---:|---|",
    ]
    by_product: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for cid in case_ids:
        meta = corpus_meta[cid]
        v = verdicts.get(cid)
        if v is None:
            L.append(f"| {cid} | {meta.get('product','?')} | — | — | — | — | (未跑) |")
            continue
        s = v.signals
        L.append(
            f"| {cid} | {meta.get('product','?')} | **{v.bucket}** | "
            f"{_path_desc(v)} | {s.n_tool_calls} | {s.n_error_tool_results} | {v.reason} |"
        )
        by_product[meta.get("product", "?")][v.bucket] += 1

    L += [
        "",
        "### 按产品聚合",
        "",
        "| Product | Cases | A | B | C | D | E? | 结论 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for prod in sorted(by_product):
        cnt = by_product[prod]
        total = sum(cnt.values())
        vals = [cnt.get(k, 0) for k in ("A", "B", "C", "D", "E?")]
        L.append(
            f"| {prod} | {total} | " + " | ".join(str(x) for x in vals) +
            f" | {_product_conclusion(cnt, total)} |"
        )

    # 缺口 top-N
    gaps = [
        (cid, corpus_meta[cid], verdicts[cid])
        for cid in case_ids
        if cid in verdicts and verdicts[cid].bucket in ("B", "C", "D", "E?")
    ]
    L += ["", "### 高频缺口 top-N (B/C/D/E?)", ""]
    if not gaps:
        L.append("_无缺口 case（全部 A - 完整命中）。_")
    else:
        for cid, meta, v in gaps:
            s = v.signals
            L.append(
                f"- **{cid}** [{meta.get('product','?')}] bucket=**{v.bucket}**: "
                f"{v.reason}  \n"
                f"  · path=`{_path_desc(v)}` · tools={s.n_tool_calls} · errors={s.n_error_tool_results}"
            )

    # Token/tool 消耗视角
    L += [
        "",
        "---",
        "",
        "## 3. Token / Tool 消耗速览",
        "",
        "| Case | Product | Bucket | Tools | Errors | Slices | WebFetch | 备注 |",
        "|---|---|:---:|---:|---:|---:|:---:|---|",
    ]
    for cid in case_ids:
        meta = corpus_meta[cid]
        v = verdicts.get(cid)
        if v is None:
            continue
        s = v.signals
        note = ""
        if s.n_error_tool_results >= 5:
            note = "⚠️ 高 error 计数 → 可能触发 fallback 循环"
        elif s.webfetch_used and not s.docsbot_called:
            note = "走 webfetch 兜底"
        L.append(
            f"| {cid} | {meta.get('product','?')} | {v.bucket} | {s.n_tool_calls} | "
            f"{s.n_error_tool_results} | {len(s.local_slice_read)} | "
            f"{'✓' if s.webfetch_used else '✗'} | {note} |"
        )

    L += [
        "",
        "> 关注 tools 数量、error 数量、slice 读取数——这三个指标与 token 消耗强相关。",
        "> Chat Path D 的高 token 消耗典型特征：多 slice + webfetch fallback + 多 tool_error。",
        "",
        "---",
        "",
        "## 4. 结论与后续",
        "",
        "**判定信号总结**：",
        f"- 触发正确性 pass rate: {n_pass}/{n_measured}",
        f"- Bucket 分布: " + ", ".join(
            f"{b}={sum(v.get(b, 0) for v in by_product.values())}"
            for b in ("A", "B", "C", "D", "E?")
        ),
        "",
        "**已知限制**：",
        f"- 本次仅覆盖 {n}/{total_corpus} 条 corpus seed，样本量小",
        "- xlsx 全量 2078 条 corpus 待接入（Task #5 · dump_corpus.py）",
        "- Bucket E?（疑似幻觉）需 LLM judge 二次确认，本工具不做",
        "",
    ]

    return "\n".join(L)


# ── main ───────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Corpus 评测覆盖报告生成器")
    ap.add_argument("--out-dir", required=True, help="eval-runs 输出目录")
    ap.add_argument("--ide", default="claude-code")
    ap.add_argument("--cases", default=str(HERE / "cases.json"))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    if not out_dir.exists():
        sys.exit(f"out-dir not found: {out_dir}")

    corpus_meta = _load_corpus_meta(Path(args.cases))
    if not corpus_meta:
        sys.exit(f"no corpus cases found in {args.cases} (tag=corpus)")

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

    # stdout 摘要
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
