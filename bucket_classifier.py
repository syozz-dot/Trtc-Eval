#!/usr/bin/env python3
"""
bucket_classifier.py — 把一条 skill 会话的 stream-json transcript 判定到
A/B/C/D/E 五个 coverage bucket，用于识别"能力覆盖缺口"。

判定完全基于静态分析（tool_use 序列 + final answer 前缀匹配），不消耗额度。

Bucket 定义:
    A - 完整命中:   docsbot could_answer=true OR 本地 slice 被 Read；且 final
                   answer 给出了有内容的 factual 回答（非拒答、非追问）
    B - 本地 KB 缺: docsbot could_answer=true，但整条链没有 Read 本地 slice
                   （意味着这题目前 **只有** docsbot 能答，本地 KB 缺覆盖）
    C - 显式拒答:   final text 明确说"当前不支持/找不到/暂无信息"之类
    D - 追问后无路: AskUserQuestion 是最后一个 tool_use / turns 用完仍在追问
    E - 疑似幻觉:   没有任何 slice Read 也没调 docsbot，但 final text 却给了
                   factual claim。需要 LLM judge 二次确认，本工具输出 "E?"

Usage:
    # 单条 transcript
    python3 bucket_classifier.py <transcript.jsonl>

    # 批量 + 汇总
    python3 bucket_classifier.py --dir eval-runs/sonnet-smoke/transcripts

    # 输出 JSON 供 coverage_report.py 聚合
    python3 bucket_classifier.py <transcript.jsonl> --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# 复用 run_eval.py 的 stream-json 解析器
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import parse_transcript, ParsedTranscript  # noqa: E402


# ── 关键字库（refusal / clarification 判定用）─────────────────────────────

REFUSAL_PATTERNS_CN = [
    "当前不支持", "暂不支持", "暂时不支持", "尚不支持",
    "本地 KB 无", "本地 kb 无", "本地知识库", "找不到相关",
    "无法回答", "抱歉，我无法", "无法提供", "没有找到",
    "guided integration 仅支持", "guided integration only supports",
    "不在覆盖范围", "不属于本 skill", "该产品的 guided integration",
]

REFUSAL_PATTERNS_EN = [
    "not currently supported", "no guided integration",
    "i don't have that information", "i don't have information",
    "unable to find", "unable to answer",
    "cannot answer", "not covered", "out of scope",
    "i couldn't find", "no information available",
]

CLARIFICATION_MARKERS = [
    "请问", "哪个平台", "哪种", "which platform", "which product",
    "please specify", "could you clarify", "you're using",
    "你用的是", "你的项目",
]


# ── 数据结构 ────────────────────────────────────────────────────────────────

@dataclass
class BucketSignals:
    docsbot_called: bool = False
    docsbot_could_answer: Optional[bool] = None   # None = 没调；True/False = 调了且看到 could_answer
    docsbot_status: Optional[str] = None
    local_slice_read: list[str] = field(default_factory=list)
    kb_resolve_called: bool = False
    webfetch_used: bool = False
    askuserquestion_used: bool = False
    askuserquestion_last_tool: bool = False
    n_tool_calls: int = 0
    n_error_tool_results: int = 0
    final_answer_len: int = 0
    final_answer_kind: str = "empty"   # factual / refusal / clarification / empty
    final_answer_preview: str = ""     # 前 200 字


@dataclass
class BucketVerdict:
    bucket: str        # "A" / "B" / "C" / "D" / "E?" / "?"
    reason: str
    signals: BucketSignals


# ── 提取最终答案文本 ─────────────────────────────────────────────────────

def _extract_final_answer(jsonl_text: str, dialect: str) -> str:
    """
    从 stream-json 里提取最终展示给用户的答案。
    优先 result event 的 result 字段（最权威），否则拼接最后一段 text_blocks。
    """
    lines = jsonl_text.splitlines()
    # 1. 找 result event
    for line in reversed(lines):
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if dialect == "claude" and e.get("type") == "result":
            r = e.get("result", "")
            if r:
                return str(r)
        if dialect == "codex" and e.get("type") == "turn.completed":
            # codex 的最终回答通常已通过 item.completed(agent_message) 输出
            break

    # 2. Fallback: 最后一个 assistant text block
    # 用 parse_transcript 拿 text_blocks（末尾就是最终回答的一部分）
    parsed = parse_transcript(jsonl_text, dialect=dialect)
    if parsed.text_blocks:
        # 最后一段最可能是"给用户的答案"
        return parsed.text_blocks[-1]
    return ""


# ── 提取信号 ────────────────────────────────────────────────────────────

_SLICE_PATH_HINTS = (
    "/slices/",
    "/references/",
    "/knowledge-base/",
    "docs/chat/",
    "docs/conference/",
    "docs/call/",
    "docs/live/",
    "docs/rtc-engine/",
)


def _looks_like_slice(path: str) -> bool:
    p = path.lower()
    return any(h in p for h in _SLICE_PATH_HINTS) and p.endswith((".md", ".yaml", ".yml"))


def _parse_docsbot_result(content: str) -> tuple[Optional[str], Optional[bool]]:
    """从 docsbot 的 tool_result stdout 里解析 status + could_answer。

    docsbot.py 输出是 pretty-printed JSON（多行），先尝试整块解析，失败再兜底扫单行。
    could_answer 字段可能不存在（老版本），此时从 status 反推：resolved → True，
    not_found/fetch_failed → False。
    """
    if not content:
        return (None, None)

    obj = None
    # 尝试整块 JSON
    stripped = content.strip()
    if stripped.startswith("{"):
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            obj = None

    # 兜底：找形如 {"status": ...} 的单行
    if obj is None:
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("{") and '"status"' in line:
                try:
                    obj = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

    if obj is None or not isinstance(obj, dict):
        return (None, None)

    status = obj.get("status")
    ca = obj.get("could_answer")
    # 老版本无 could_answer → 从 status 反推
    if ca is None and status:
        if status == "resolved":
            ca = True
        elif status in ("not_found", "fetch_failed"):
            ca = False
    return (status, ca)


def _classify_final_answer(text: str) -> tuple[str, str]:
    """
    返回 (kind, preview)。
    kind: factual / refusal / clarification / empty
    """
    text = (text or "").strip()
    preview = text[:200]
    if not text:
        return ("empty", "")
    lower = text.lower()

    # 拒答：命中任一 refusal 关键词
    for p in REFUSAL_PATTERNS_CN + REFUSAL_PATTERNS_EN:
        if p.lower() in lower:
            return ("refusal", preview)

    # 追问：文本以问号结尾 OR 命中 clarification 标记
    ends_with_q = text.rstrip().endswith(("?", "？"))
    has_clar_marker = any(m in text for m in CLARIFICATION_MARKERS)
    if ends_with_q and (has_clar_marker or len(text) < 200):
        return ("clarification", preview)

    # 兜底：有内容且非拒答非追问 → 视作 factual
    return ("factual", preview)


def extract_signals(jsonl_text: str, dialect: str = "claude") -> BucketSignals:
    parsed = parse_transcript(jsonl_text, dialect=dialect)
    sig = BucketSignals()

    sig.n_tool_calls = len(parsed.tool_calls)
    sig.n_error_tool_results = sum(1 for r in parsed.tool_results.values() if r.is_error)

    # 顺序遍历 tool_calls
    for i, tc in enumerate(parsed.tool_calls):
        name = tc.name
        input_dict = tc.input or {}

        if name == "Bash":
            cmd = input_dict.get("command", "") or ""
            if "docsbot" in cmd:
                sig.docsbot_called = True
                # 找对应 tool_result 解析 could_answer
                tr = parsed.tool_results.get(tc.id)
                if tr:
                    status, ca = _parse_docsbot_result(tr.content)
                    # 一次会话可能多次调 docsbot；只要有一次 could_answer=true 就算 true
                    if ca is True:
                        sig.docsbot_could_answer = True
                    elif ca is False and sig.docsbot_could_answer is None:
                        sig.docsbot_could_answer = False
                    if status and not sig.docsbot_status:
                        sig.docsbot_status = status
            if "tools.kb" in cmd or "tools/kb.py" in cmd:
                sig.kb_resolve_called = True

        elif name == "Read":
            fp = input_dict.get("file_path", "") or ""
            if _looks_like_slice(fp):
                sig.local_slice_read.append(fp)

        elif name == "WebFetch":
            sig.webfetch_used = True

        elif name == "AskUserQuestion":
            sig.askuserquestion_used = True
            # 是不是最后一个 tool_use？
            if i == len(parsed.tool_calls) - 1:
                sig.askuserquestion_last_tool = True

    # final answer
    final = _extract_final_answer(jsonl_text, dialect)
    sig.final_answer_len = len(final)
    sig.final_answer_kind, sig.final_answer_preview = _classify_final_answer(final)

    return sig


# ── 判定 ────────────────────────────────────────────────────────────────

def classify(signals: BucketSignals) -> BucketVerdict:
    """
    按优先级判定 bucket。
    规则顺序：先看 final_answer_kind（refusal/clarification/empty 都是终局），
    再看有内容的 factual answer 配上哪种检索源。tool 序列（比如"最后一个是
    AskUserQuestion"）只作为 supporting signal，不单独决定 bucket——因为用户
    完全可能在 AskUserQuestion 之后继续 flow，skill 也可能给出 factual 答案。
    """
    kind = signals.final_answer_kind

    # D — 追问后无路：final 是追问，或 final 为空且用过 AskUserQuestion
    if kind == "clarification":
        return BucketVerdict(
            bucket="D",
            reason="final message is a clarification question",
            signals=signals,
        )
    if kind == "empty" and signals.askuserquestion_used:
        return BucketVerdict(
            bucket="D",
            reason="empty final message after AskUserQuestion — user did not proceed",
            signals=signals,
        )

    # C — 显式拒答
    if kind == "refusal":
        return BucketVerdict(
            bucket="C",
            reason="skill explicitly refused / said unavailable",
            signals=signals,
        )

    # A / B — factual 回答，看检索源
    hit_docsbot = signals.docsbot_could_answer is True
    hit_slice = len(signals.local_slice_read) > 0

    if kind == "factual":
        if hit_docsbot and hit_slice:
            return BucketVerdict(
                bucket="A",
                reason=f"docsbot resolved + {len(signals.local_slice_read)} local slice(s) read",
                signals=signals,
            )
        if hit_slice and not hit_docsbot:
            return BucketVerdict(
                bucket="A",
                reason=f"answered from {len(signals.local_slice_read)} local slice(s)",
                signals=signals,
            )
        if hit_docsbot and not hit_slice:
            # docsbot 能答但本地 KB 缺 —— 是覆盖缺口信号（未来 docsbot quota 挤压时会失守）
            return BucketVerdict(
                bucket="B",
                reason="docsbot resolved but no local slice — local KB coverage gap",
                signals=signals,
            )
        # docsbot 被调但 could_answer=False，且无本地 slice
        if signals.docsbot_called and signals.docsbot_could_answer is False:
            return BucketVerdict(
                bucket="C",
                reason=f"docsbot could not answer (status={signals.docsbot_status!r}) and no local fallback — coverage gap",
                signals=signals,
            )
        # WebFetch 兜底也算"外部检索源"，归 B（本地 KB 缺）
        if signals.webfetch_used:
            return BucketVerdict(
                bucket="B",
                reason="answered via WebFetch fallback (no docsbot, no local slice)",
                signals=signals,
            )
        # 完全没检索源却给 factual 答案 → E?
        return BucketVerdict(
            bucket="E?",
            reason="factual answer without any retrieval source — possible hallucination, needs LLM judge",
            signals=signals,
        )

    # 兜底
    return BucketVerdict(
        bucket="?",
        reason=f"cannot classify (final={kind}, tools={signals.n_tool_calls})",
        signals=signals,
    )


# ── 单文件入口 + 批量入口 ────────────────────────────────────────────────

def classify_file(path: Path, dialect: str = "claude") -> BucketVerdict:
    text = path.read_text(encoding="utf-8", errors="replace")
    sig = extract_signals(text, dialect=dialect)
    return classify(sig)


def _fmt_short_verdict(verdict: BucketVerdict, tag: str = "") -> str:
    s = verdict.signals
    docsbot = "?"
    if s.docsbot_called:
        docsbot = "T" if s.docsbot_could_answer else ("F" if s.docsbot_could_answer is False else "?")
    slices = len(s.local_slice_read)
    return (
        f"  [{verdict.bucket:>2}] {tag}\n"
        f"       final_kind={s.final_answer_kind:<13}  len={s.final_answer_len:>5}  "
        f"tools={s.n_tool_calls:>2}  errors={s.n_error_tool_results}\n"
        f"       docsbot={docsbot:<3}  slice_reads={slices:<2}  "
        f"webfetch={'Y' if s.webfetch_used else 'N'}  askuser={'Y' if s.askuserquestion_used else 'N'}\n"
        f"       reason: {verdict.reason}\n"
        f"       preview: {s.final_answer_preview[:120]!r}"
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Bucket classifier for TRTC skill transcripts")
    p.add_argument("path", nargs="?", help="Single transcript .jsonl to classify")
    p.add_argument("--dir", help="Directory of .jsonl transcripts to classify in batch")
    p.add_argument("--dialect", default="claude",
                   choices=["claude", "cursor", "codex"],
                   help="stream-json dialect")
    p.add_argument("--json", action="store_true",
                   help="Output structured JSON (for pipeline consumption)")
    args = p.parse_args()

    if not args.path and not args.dir:
        p.error("must provide a transcript path or --dir")

    targets: list[Path] = []
    if args.path:
        targets.append(Path(args.path))
    if args.dir:
        targets.extend(sorted(Path(args.dir).glob("*.jsonl")))

    if not targets:
        sys.exit("no transcripts to classify")

    verdicts = []
    for t in targets:
        try:
            v = classify_file(t, dialect=args.dialect)
        except Exception as e:
            print(f"  [ERR] {t.name}: {e}", file=sys.stderr)
            continue
        verdicts.append((t, v))

    if args.json:
        out = [
            {"file": str(t), "verdict": asdict(v)}
            for t, v in verdicts
        ]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # 人类可读输出
    print(f"Classified {len(verdicts)} transcript(s):")
    print()
    bucket_counts: dict[str, int] = {}
    for t, v in verdicts:
        print(_fmt_short_verdict(v, tag=t.name))
        print()
        bucket_counts[v.bucket] = bucket_counts.get(v.bucket, 0) + 1

    print("─" * 60)
    print("Bucket 分布:")
    total = len(verdicts)
    labels = {
        "A": "A - 完整命中",
        "B": "B - 本地 KB 缺",
        "C": "C - 显式拒答",
        "D": "D - 追问后无路",
        "E?": "E? - 疑似幻觉（待 LLM judge）",
        "?": "? - 未分类",
    }
    for b in ("A", "B", "C", "D", "E?", "?"):
        n = bucket_counts.get(b, 0)
        pct = 100.0 * n / total if total else 0
        print(f"  {labels[b]:<32}  {n:>3}  ({pct:5.1f}%)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
