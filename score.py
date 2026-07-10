#!/usr/bin/env python3
"""
score.py — Phase 2 eval scorer (v2, cases.json v2.0).

读填好的 results.<ide>.yaml，产出：
  - stdout：人读评测报告
  - summary.json：结构化摘要（可作为下次 baseline）

新增（v2）：
  - 支持多轮 case（turns 分组）与单轮 case（扁平 observations）
  - 按 IDE 能力自动跳过维度（obs_keys.requires 与 ide_profiles.capabilities 匹配）
  - 空 yaml（全 ?）标 incomplete，不再静默 PASS
  - 智能 baseline 对比：case 结构变了自动跳过 delta，不当回归
  - 报告中每条 case 显示"通过维度 / 总维度 / 跳过维度"三项

Usage:
    python3 score.py results.claude-code.yaml
    python3 score.py results.cursor.yaml --baseline prev_summary.json
    python3 score.py results.<ide>.yaml --cases cases.json --out-dir ./reports
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
PASS_THRESHOLD = 1.0            # case pass = 加权分 == 1.0（即所有 hard 观察点都是 Y）
INCOMPLETE_THRESHOLD = 0.5      # 未填比例 > 此值则标 incomplete，不进 pass/fail 统计


# ── 观察点权重分级 ─────────────────────────────────────────────────────────
# 三档：
#   critical: 主 skill 未触发 → 整 case 直接 fail，其他维度不用看
#   major:    正常权重 1.0，正常拉分
#   minor:    权重 0.5，弱信号（追问关键词等）
#
# 权重只影响 score 数值展示（可视化用），不影响 pass/fail 判定。

OBS_TIER = {
    "route_triggered":       "critical",  # trtc 主 skill 是否被激活
    "reporting_called":      "major",
    "hooks_guarded":         "major",
    "session_state":         "major",
    "trace_assertions":      "major",  # Phase 3 白盒断言 — 内部契约 fail 应当 flip case
    "route_level1":          "minor",
    "route_level2":          "minor",
    "clarification_raised":  "minor",
    "tools_called":          "minor",
}
TIER_WEIGHT = {"critical": 1.0, "major": 1.0, "minor": 0.5}

# ── pass 判定分组（独立于权重）────────────────────────────────────────────
# SOFT_OBS: 这些观察点 N 时 → 记录 (minor concern)，但不 flip case 到 fail
#           适合"路由到子 skill 是否对"这类还没优化好的判定，先记录不阻塞。
# 其他所有观察点 N → 会拖 case 到 fail（含 critical 短路）。
SOFT_OBS = {"route_level1", "route_level2"}


# ── yaml loader ──────────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
        return yaml.safe_load(text)
    except Exception as e:
        sys.exit(f"Failed to parse {path}: {e}\n  Install pyyaml: pip install pyyaml")


# ── data types ───────────────────────────────────────────────────────────────

@dataclass
class DimResult:
    """一个 (turn, obs_key) 的判定结果。turn=None 表示单轮 case 或 case_level。"""
    turn: int | None
    key: str
    value: str
    status: str      # "pass" / "fail" / "skip_user" / "skip_capability" / "unfilled"
    skip_reason: str = ""
    reason: str = ""    # judge 给的详细原因（可选，来自 observation_reasons）

    @property
    def tier(self) -> str:
        return OBS_TIER.get(self.key.replace("case:", ""), "minor")

    @property
    def weight(self) -> float:
        return TIER_WEIGHT[self.tier]


@dataclass
class CaseResult:
    case_id: str
    dims: list[DimResult] = field(default_factory=list)
    notes: str = ""
    status: str = "pass"     # "pass" / "fail" / "incomplete" / "skipped_capability"
    skip_reason: str = ""
    fail_reason: str = ""    # 明确定位到哪个观察点导致 fail

    @property
    def active_dims(self) -> list[DimResult]:
        """有效观察点：既没被用户 skip 也没被能力 skip 也没未填。"""
        return [d for d in self.dims if d.status in ("pass", "fail")]

    @property
    def unfilled_dims(self) -> list[DimResult]:
        return [d for d in self.dims if d.status == "unfilled"]

    @property
    def failed_dims(self) -> list[DimResult]:
        return [d for d in self.dims if d.status == "fail"]

    @property
    def hard_failed(self) -> list[DimResult]:
        """会拖 case 到 fail 的观察点（不含 SOFT_OBS）。"""
        return [d for d in self.failed_dims if d.key.replace("case:", "") not in SOFT_OBS]

    @property
    def soft_failed(self) -> list[DimResult]:
        """SOFT_OBS 里 N 的观察点：记录但不拖 case fail（minor concern）。"""
        return [d for d in self.failed_dims if d.key.replace("case:", "") in SOFT_OBS]

    @property
    def critical_failed(self) -> list[DimResult]:
        return [d for d in self.hard_failed if d.tier == "critical"]

    @property
    def score(self) -> float:
        """加权分：passed_weight / total_weight（仅计有效观察点）。"""
        act = self.active_dims
        if not act:
            return 0.0
        total_w = sum(d.weight for d in act)
        pass_w = sum(d.weight for d in act if d.status == "pass")
        return pass_w / total_w if total_w > 0 else 0.0


# ── value classification ─────────────────────────────────────────────────────

def _classify_value(v) -> tuple[str, str]:
    """把用户填的 Y/N/S/? 归到 (status, normalized_value)。"""
    s = str(v).strip().upper()
    if s in ("Y", "YES", "TRUE", "1"):
        return ("pass", s)
    if s in ("N", "NO", "FALSE", "0"):
        return ("fail", s)
    if s in ("S", "SKIP"):
        return ("skip_user", s)
    if s in ("?", "", "NONE"):
        return ("unfilled", s or "?")
    # 未识别值当 fail，但保留原值方便调试
    return ("fail", s)


# ── capability filtering ─────────────────────────────────────────────────────

def _obs_key_requires(obs_dict: dict, key: str) -> list[str]:
    entry = obs_dict.get(key, {})
    return entry.get("requires", []) if isinstance(entry, dict) else []


def _lacks_capability(required: list[str], available: set[str]) -> list[str]:
    return [c for c in required if c not in available]


# ── scoring ──────────────────────────────────────────────────────────────────

def score_case(
    entry: dict,
    obs_dict: dict,
    ide_capabilities: set[str],
) -> CaseResult:
    cid = entry.get("case_id", "?")
    result = CaseResult(case_id=cid, notes=entry.get("notes", "") or "")

    # 显式跳过整条 case（用户手工写 skipped: true）
    if entry.get("skipped"):
        result.status = "skipped_capability"
        result.skip_reason = "user marked skipped"
        return result

    # IDE 能力级跳过整条 case（case 声明的 required capabilities）
    case_req = entry.get("ide_capabilities_required", [])
    if case_req:
        missing = _lacks_capability(case_req, ide_capabilities)
        if missing:
            result.status = "skipped_capability"
            result.skip_reason = f"IDE lacks: {', '.join(missing)}"
            return result

    # 收集观察点：单轮扁平 or 多轮 turns
    def _collect_obs(observations: dict, reasons: dict, turn_id: int | None) -> None:
        for k, v in observations.items():
            status, norm = _classify_value(v)
            reason = reasons.get(k, "") if isinstance(reasons, dict) else ""

            # 若维度需要 IDE 不具备的能力，覆盖为 skip_capability
            missing = _lacks_capability(_obs_key_requires(obs_dict, k), ide_capabilities)
            if missing:
                result.dims.append(DimResult(
                    turn=turn_id, key=k, value=norm,
                    status="skip_capability",
                    skip_reason=f"lacks {', '.join(missing)}",
                    reason=reason,
                ))
                continue

            result.dims.append(DimResult(
                turn=turn_id, key=k, value=norm, status=status,
                reason=reason,
            ))

    if "turns" in entry:
        for t in entry["turns"]:
            _collect_obs(
                t.get("observations", {}),
                t.get("observation_reasons", {}),
                t.get("turn"),
            )
    elif "observations" in entry:
        _collect_obs(
            entry["observations"],
            entry.get("observation_reasons", {}),
            None,
        )

    # case_level 期望
    case_level = entry.get("case_level", {}) or {}
    for k, v in case_level.items():
        status, norm = _classify_value(v)
        result.dims.append(DimResult(
            turn=None, key=f"case:{k}", value=norm, status=status
        ))

    # 判 incomplete / pass / fail
    total = len(result.dims)
    if total == 0:
        result.status = "incomplete"
        result.skip_reason = "no observations"
        return result

    unfilled = len(result.unfilled_dims)
    if unfilled == total:
        result.status = "incomplete"
        result.skip_reason = "all unfilled"
    elif unfilled / total > INCOMPLETE_THRESHOLD:
        result.status = "incomplete"
        result.skip_reason = f"{unfilled}/{total} unfilled"
    else:
        act = result.active_dims
        if not act:
            # 全 skip_capability + 剩下 unfilled — 视为跳过
            result.status = "skipped_capability"
            result.skip_reason = "all dims skipped or unfilled"
        else:
            # ── 新规则 ──
            # 1. critical 短路：主 skill 未触发 → 整 case 直接 fail，其他维度不用看
            crit_fail = result.critical_failed
            if crit_fail:
                result.status = "fail"
                keys = ", ".join(_dim_ref(d) for d in crit_fail)
                result.fail_reason = f"[CRITICAL] {keys}"
            else:
                # 2. hard 观察点全 Y → pass；任一 hard N → fail。
                #    soft 观察点（SOFT_OBS）N 只记录 concern，不拖 fail。
                hard_fail = result.hard_failed
                if hard_fail:
                    result.status = "fail"
                    keys = ", ".join(_dim_ref(d) for d in hard_fail)
                    result.fail_reason = keys
                else:
                    result.status = "pass"

    return result


def _dim_ref(d: DimResult) -> str:
    """把维度渲染成 'route_level1@turn2' / 'reporting_called' 这种引用。"""
    if d.turn is not None:
        return f"{d.key}@turn{d.turn}"
    return d.key


# ── baseline structure comparison ────────────────────────────────────────────

def _structure_signature(case_entry: dict) -> str:
    """给 baseline case 生成结构签名，用于识别 case 结构是否变了。"""
    if "turns" in case_entry:
        n = len(case_entry.get("turns", []))
        return f"multi-{n}"
    if "dims" in case_entry:
        # 从 baseline 里恢复的
        turns = {d.get("turn") for d in case_entry["dims"] if isinstance(d, dict)}
        if turns == {None}:
            return "single"
        return f"multi-{len([t for t in turns if t is not None])}"
    if "observations" in case_entry:
        return "single"
    return "unknown"


def _current_structure(cr: CaseResult) -> str:
    turns = {d.turn for d in cr.dims}
    if turns - {None}:
        return f"multi-{len(turns - {None})}"
    return "single"


# ── report ───────────────────────────────────────────────────────────────────

STATUS_ICON = {
    "pass": "\033[32m✓\033[0m",
    "fail": "\033[31m✗\033[0m",
    "incomplete": "\033[33m…\033[0m",
    "skipped_capability": "\033[2m─\033[0m",
}
DIM_ICON = {
    "pass": "\033[32m  ✓\033[0m",
    "fail": "\033[31m  ✗\033[0m",
    "skip_user": "\033[2m  ─\033[0m",
    "skip_capability": "\033[2m  ⊘\033[0m",
    "unfilled": "\033[33m  ?\033[0m",
}


def _strip_ansi_if_pipe():
    """管道输出时去掉 ANSI 颜色。"""
    if sys.stdout.isatty():
        return
    for k in list(STATUS_ICON):
        STATUS_ICON[k] = STATUS_ICON[k].replace("\033[32m", "").replace("\033[31m", "") \
            .replace("\033[33m", "").replace("\033[2m", "").replace("\033[0m", "")
    for k in list(DIM_ICON):
        DIM_ICON[k] = DIM_ICON[k].replace("\033[32m", "").replace("\033[31m", "") \
            .replace("\033[33m", "").replace("\033[2m", "").replace("\033[0m", "")


def print_report(results: list[CaseResult], meta: dict, baseline: dict | None) -> None:
    _strip_ansi_if_pipe()
    W = 76
    ide = meta.get("ide", "?")
    tester = meta.get("tester", "?")
    date = meta.get("date", "?")

    print(f"\n{'─' * W}")
    print(f"  TRTC Skill · Phase 2 评测报告")
    print(f"  IDE: {ide}    测试人: {tester}    日期: {date}")
    print(f"  评分规则:  hard 观察点全 Y → pass；任一 hard N → fail（critical 短路）")
    print(f"           soft 观察点(N 不拖 fail): {', '.join(sorted(SOFT_OBS))}")
    print(f"           权重 (仅可视化): critical={TIER_WEIGHT['critical']} · major={TIER_WEIGHT['major']} · minor={TIER_WEIGHT['minor']}")
    print(f"{'─' * W}")

    baseline_cases = {c["case_id"]: c for c in (baseline or {}).get("cases", [])}

    for r in results:
        icon = STATUS_ICON.get(r.status, "?")
        n_pass = sum(1 for d in r.active_dims if d.status == "pass")
        n_active = len(r.active_dims)
        n_skip_cap = sum(1 for d in r.dims if d.status == "skip_capability")
        n_unfilled = len(r.unfilled_dims)

        header = f"\n  [{icon}] {r.case_id}"
        if r.status == "skipped_capability":
            print(f"{header}  ─  {r.skip_reason}")
            continue
        if r.status == "incomplete":
            print(f"{header}  ({n_pass}/{n_active} pass, {n_unfilled} 未填)  {r.skip_reason}")
        else:
            score_txt = f"score={r.score:.2f}"
            extras = []
            if n_skip_cap:
                extras.append(f"{n_skip_cap} 跳过(能力)")
            if n_unfilled:
                extras.append(f"{n_unfilled} 未填")
            if r.status == "pass" and r.soft_failed:
                extras.append(f"{len(r.soft_failed)} minor concern")
            extras_str = f"  ({', '.join(extras)})" if extras else ""
            print(f"{header}  {score_txt}  {n_pass}/{n_active} pass{extras_str}")
            if r.status == "fail" and r.fail_reason:
                print(f"        ✗ FAIL: {r.fail_reason}")

        # 分 turn 展示
        turn_ids = sorted({d.turn for d in r.dims}, key=lambda x: (x is None, x))
        for tid in turn_ids:
            group = [d for d in r.dims if d.turn == tid]
            if tid is not None:
                print(f"     ─ turn {tid}")
            for d in group:
                icon = DIM_ICON.get(d.status, "?")
                # 用 · 星号标注 tier：critical=★  major=(空)  minor=·
                tier_mark = {"critical": "★", "major": " ", "minor": "·"}.get(d.tier, " ")
                if d.status == "fail":
                    print(f"     {icon} {tier_mark} {d.key} → 填的是 {d.value!r}")
                elif d.status == "skip_capability":
                    print(f"     {icon} {tier_mark} {d.key}  (跳过：{d.skip_reason})")
                elif d.status == "skip_user":
                    print(f"     {icon} {tier_mark} {d.key}  (跳过)")
                elif d.status == "unfilled":
                    print(f"     {icon} {tier_mark} {d.key}  (未填)")
                else:
                    print(f"     {icon} {tier_mark} {d.key}")

        if r.notes:
            print(f"          备注: {r.notes}")

        # baseline 对比
        prev = baseline_cases.get(r.case_id)
        if prev and r.status in ("pass", "fail"):
            prev_sig = _structure_signature(prev)
            curr_sig = _current_structure(r)
            if prev_sig != curr_sig:
                print(f"          vs baseline: 结构变了 ({prev_sig} → {curr_sig})，跳过增量")
            else:
                prev_score = prev.get("score", 0.0)
                delta = r.score - prev_score
                arrow = "↑" if delta > 0.01 else ("↓" if delta < -0.01 else "→")
                print(f"          vs baseline: {prev_score:.2f} {arrow} {r.score:.2f}  [{prev.get('ide','?')}]")

    # 汇总
    n_total = len(results)
    n_pass = sum(1 for r in results if r.status == "pass")
    n_fail = sum(1 for r in results if r.status == "fail")
    n_incomplete = sum(1 for r in results if r.status == "incomplete")
    n_skipped = sum(1 for r in results if r.status == "skipped_capability")
    n_critical_fail = sum(1 for r in results if r.critical_failed)

    scored = [r for r in results if r.status in ("pass", "fail")]
    avg = sum(r.score for r in scored) / len(scored) if scored else 0.0

    print(f"\n{'─' * W}")
    line = f"  总计: {n_pass} pass · {n_fail} fail"
    if n_critical_fail:
        line += f" (含 {n_critical_fail} critical)"
    if n_incomplete:
        line += f" · {n_incomplete} incomplete"
    if n_skipped:
        line += f" · {n_skipped} skipped"
    line += f"    avg_score={avg:.2f}   (共 {n_total} 条)"
    print(line)

    # FAIL 明细一屏可视 —— 立即定位到 case 和 观察点
    failed = [r for r in results if r.status == "fail"]
    if failed:
        print(f"\n  FAIL 明细：")
        for r in failed:
            marker = "★ " if r.critical_failed else "  "
            print(f"    {marker}{r.case_id}:")
            for d in r.failed_dims:
                if d.key.replace("case:", "") in SOFT_OBS:
                    continue
                key = d.key.replace("case:", "")
                turn_marker = f" @turn{d.turn}" if d.turn is not None else ""
                reason = d.reason or "(no reason recorded)"
                print(f"       ✗ {key}{turn_marker} — {reason}")

    # SKIP 明细 —— 让"未启用/能力不足"透明可见
    skipped_dims = [
        (r, d) for r in results for d in r.dims
        if d.status in ("skip_user", "skip_capability")
    ]
    if skipped_dims:
        print(f"\n  跳过明细（不影响 pass/fail）：")
        for r, d in skipped_dims:
            key = d.key.replace("case:", "")
            turn_marker = f" @turn{d.turn}" if d.turn is not None else ""
            if d.status == "skip_capability":
                reason = f"IDE 能力不支持（{d.skip_reason}）"
            else:
                reason = d.reason or "运行时跳过"
            print(f"      ─ {r.case_id} · {key}{turn_marker} — {reason}")

    # Minor concern 汇总（pass 但 route_level* 观察点 N 的 case）—— 记录不告警
    concerns = [r for r in results if r.status == "pass" and r.soft_failed]
    if concerns:
        print(f"\n  待关注（不影响 pass，但值得记录）：")
        for r in concerns:
            keys = ", ".join(_dim_ref(d) for d in r.soft_failed)
            print(f"      {r.case_id}: {keys}")

    if baseline:
        prev_scored = [c for c in baseline.get("cases", []) if c.get("status") in ("pass", "fail")]
        prev_avg = sum(c.get("score", 0.0) for c in prev_scored) / max(len(prev_scored), 1)
        d = avg - prev_avg
        arrow = "↑" if d > 0.01 else ("↓" if d < -0.01 else "→")
        print(f"  vs baseline [{baseline.get('ide','?')}]: {prev_avg:.2f} {arrow} {avg:.2f}")

    print(f"{'─' * W}\n")


def format_report_markdown(results: list[CaseResult], meta: dict, baseline: dict | None) -> str:
    """Render the same data print_report emits, but as GitHub-flavored markdown.

    Layout:
      - status callout line (✅ / ❌ / ⚠️)
      - summary sentence
      - case table (Case | Score | Result | 观察点)
      - <details> collapsible for evaluation rules
      - fail detail section (only if any hard-failed)
      - minor-concern list (only if any soft-failed)
      - baseline delta line (only if baseline present)
    """
    ide = meta.get("ide", "?")
    tester = meta.get("tester", "?")
    date = meta.get("date", "?")

    scored = [r for r in results if r.status in ("pass", "fail")]
    n_pass = sum(1 for r in results if r.status == "pass")
    n_fail = sum(1 for r in results if r.status == "fail")
    n_incomplete = sum(1 for r in results if r.status == "incomplete")
    n_skipped = sum(1 for r in results if r.status == "skipped_capability")
    n_critical = sum(1 for r in results if r.critical_failed)
    avg = sum(r.score for r in scored) / len(scored) if scored else 0.0

    if n_critical:
        headline = f"❌ **{n_critical} critical fail** · {n_fail} fail · {n_pass} pass"
    elif n_fail:
        headline = f"❌ **{n_fail} fail** · {n_pass} pass"
    elif n_incomplete:
        headline = f"⚠️ **{n_incomplete} incomplete** · {n_pass} pass"
    else:
        headline = f"✅ **{n_pass}/{len(results)} pass** · avg={avg:.2f}"

    lines: list[str] = []
    lines.append(f"**IDE:** `{ide}`   **测试人:** `{tester}`   **日期:** `{date}`")
    lines.append("")
    lines.append(headline)
    lines.append("")

    # ── Case table ──────────────────────────────────────────────────────────
    lines.append("| Case | Result | Score | 观察点 |")
    lines.append("|---|---|---|---|")

    baseline_cases = {c["case_id"]: c for c in (baseline or {}).get("cases", [])}

    # Which observation keys are Phase 3 signals — get a [P3] prefix in the
    # markdown observation column so P2 vs P3 is visually distinct.
    PHASE3_OBS = {"trace_assertions"}

    def _obs_label(key: str) -> str:
        return f"[P3] {key}" if key in PHASE3_OBS else key

    def _obs_summary(r: CaseResult) -> str:
        """Compact one-cell observation summary, tier icons preserved."""
        parts: list[str] = []
        for d in r.dims:
            key = d.key.replace("case:", "")
            label = _obs_label(key)
            if d.status == "pass":
                parts.append(f"✓ {label}")
            elif d.status == "fail":
                mark = "★" if d.tier == "critical" else ("·" if d.tier == "minor" else "")
                parts.append(f"✗ {mark}{label}".strip())
            elif d.status == "skip_capability":
                parts.append(f"─ {label} (跳过)")
            elif d.status == "skip_user":
                parts.append(f"─ {label} (未启用)")
            elif d.status == "unfilled":
                parts.append(f"? {label}")
        return " · ".join(parts) if parts else "—"

    for r in results:
        if r.status == "pass":
            result_cell = "✅ pass" + (f" ({len(r.soft_failed)} concern)" if r.soft_failed else "")
        elif r.status == "fail":
            result_cell = "❌ CRITICAL" if r.critical_failed else "❌ fail"
        elif r.status == "incomplete":
            result_cell = "⚠️ incomplete"
        elif r.status == "skipped_capability":
            result_cell = "⊘ skipped"
        else:
            result_cell = r.status

        score_cell = f"{r.score:.2f}" if r.status in ("pass", "fail") else "—"

        # baseline delta arrow inline with score
        prev = baseline_cases.get(r.case_id)
        if prev and r.status in ("pass", "fail"):
            prev_sig = _structure_signature(prev)
            curr_sig = _current_structure(r)
            if prev_sig == curr_sig:
                delta = r.score - prev.get("score", 0.0)
                arrow = "↑" if delta > 0.01 else ("↓" if delta < -0.01 else "→")
                score_cell = f"{r.score:.2f} {arrow}"

        lines.append(f"| `{r.case_id}` | {result_cell} | {score_cell} | {_obs_summary(r)} |")

    lines.append("")

    # ── Fail detail (only if any) ────────────────────────────────────────────
    failed = [r for r in results if r.status == "fail"]
    if failed:
        lines.append("### ❌ FAIL 明细")
        lines.append("")
        for r in failed:
            marker = "**★ CRITICAL**" if r.critical_failed else "**FAIL**"
            lines.append(f"- {marker} `{r.case_id}`")
            # Show each failed observation with its judge's reason (drill-down)
            for d in r.failed_dims:
                if d.key.replace("case:", "") in SOFT_OBS:
                    continue  # soft failures are minor concerns, shown separately
                key = d.key.replace("case:", "")
                label = _obs_label(key)
                turn_marker = f" @turn{d.turn}" if d.turn is not None else ""
                reason = d.reason or "(no reason recorded)"
                lines.append(f"  - ✗ `{label}`{turn_marker} — {reason}")
        lines.append("")

    # ── Skipped observations (call out P3 未启用 / IDE 能力不支持) ────────────
    # Only surface skips that came from a live obs judgement (skip_user or
    # skip_capability). unfilled skips (user never scored) are already caught
    # by the incomplete status; not worth surfacing again.
    skipped_dims: list[tuple[CaseResult, DimResult]] = []
    for r in results:
        for d in r.dims:
            if d.status in ("skip_user", "skip_capability"):
                skipped_dims.append((r, d))
    if skipped_dims:
        lines.append("### ─ 跳过明细（不影响 pass/fail）")
        lines.append("")
        for r, d in skipped_dims:
            key = d.key.replace("case:", "")
            label = _obs_label(key)
            turn_marker = f" @turn{d.turn}" if d.turn is not None else ""
            if d.status == "skip_capability":
                reason = f"IDE 能力不支持（{d.skip_reason}）"
            else:
                # skip_user — reason comes from judge (e.g. Phase 3 not activated)
                reason = d.reason or "运行时跳过"
            lines.append(f"- `{r.case_id}` · `{label}`{turn_marker} — {reason}")
        lines.append("")

    # ── Minor concern (only if any) ─────────────────────────────────────────
    concerns = [r for r in results if r.status == "pass" and r.soft_failed]
    if concerns:
        lines.append("### 待关注（不影响 pass · soft 观察点 N）")
        lines.append("")
        for r in concerns:
            for d in r.soft_failed:
                key = d.key.replace("case:", "")
                turn_marker = f" @turn{d.turn}" if d.turn is not None else ""
                reason = d.reason or "(no reason recorded)"
                lines.append(f"- `{r.case_id}` · `{key}`{turn_marker} — {reason}")
        lines.append("")

    # ── Baseline overall delta ──────────────────────────────────────────────
    if baseline:
        prev_scored = [c for c in baseline.get("cases", []) if c.get("status") in ("pass", "fail")]
        prev_avg = sum(c.get("score", 0.0) for c in prev_scored) / max(len(prev_scored), 1)
        d = avg - prev_avg
        arrow = "↑" if d > 0.01 else ("↓" if d < -0.01 else "→")
        lines.append(f"**vs baseline** (`{baseline.get('ide','?')}`): `{prev_avg:.2f} {arrow} {avg:.2f}`")
        lines.append("")

    # ── Evaluation rules, collapsible so it doesn't dominate ────────────────
    lines.append("<details><summary>评分规则 · 观察点分类</summary>")
    lines.append("")
    lines.append("- **hard 观察点全 Y → pass**；任一 hard N → fail")
    lines.append(f"- **critical** ({', '.join(sorted(k for k, v in OBS_TIER.items() if v == 'critical'))}) N 时短路 fail")
    lines.append(f"- **soft** ({', '.join(sorted(SOFT_OBS))}) N 只记录 minor concern，不拖 fail")
    lines.append(f"- 权重（仅可视化）：critical={TIER_WEIGHT['critical']} · major={TIER_WEIGHT['major']} · minor={TIER_WEIGHT['minor']}")
    lines.append("")
    lines.append("</details>")
    lines.append("")

    return "\n".join(lines)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Score filled Phase 2 results.yaml (v2)")
    parser.add_argument("results", help="Path to filled results.<ide>.yaml")
    parser.add_argument("--baseline", help="Previous summary.json for comparison")
    parser.add_argument("--cases", default=str(HERE / "cases.json"),
                        help="Path to cases.json (for obs_keys / ide_profiles)")
    parser.add_argument("--out-dir", help="Output directory for summary.json (default: results dir)")
    parser.add_argument("--format", choices=["cli", "markdown"], default="cli",
                        help="Output format. 'cli' (default) prints the ANSI-colored console report; "
                             "'markdown' prints a GitHub-flavored markdown report (used by CI).")
    args = parser.parse_args()

    results_path = Path(args.results)
    if not results_path.exists():
        sys.exit(f"Not found: {results_path}")

    cases_path = Path(args.cases)
    if not cases_path.exists():
        sys.exit(f"cases.json not found: {cases_path}\n  Pass --cases <path>")

    data = _load_yaml(results_path)
    if not isinstance(data, dict):
        sys.exit(f"Invalid yaml structure: {results_path}")

    with open(cases_path) as f:
        cases_data = json.load(f)

    obs_dict = cases_data.get("obs_keys", {})
    ide_profiles = cases_data.get("ide_profiles", {})

    ide = data.get("ide", "").strip()
    if ide.startswith("<"):
        ide = ""
    profile = ide_profiles.get(ide, {})
    ide_caps = set(profile.get("capabilities", []))
    if not ide_caps:
        print(f"[warn] Unknown IDE '{ide}' — treating as full-capability", file=sys.stderr)
        # 保守假设：不知道的 IDE 当作全能力，避免误跳过
        ide_caps = {"headless", "tool_use_events", "hooks", "session_file"}

    meta = {k: str(v) for k, v in data.items() if k != "cases"}
    entries = data.get("cases", [])

    results = [score_case(e, obs_dict, ide_caps) for e in entries]

    baseline = None
    if args.baseline:
        bp = Path(args.baseline)
        if bp.exists():
            with open(bp) as f:
                baseline = json.load(f)
        else:
            print(f"[warn] baseline not found: {bp}", file=sys.stderr)

    print_report(results, meta, baseline) if args.format == "cli" else print(format_report_markdown(results, meta, baseline))

    # summary.json
    scored = [r for r in results if r.status in ("pass", "fail")]
    n_pass = sum(1 for r in results if r.status == "pass")
    n_fail = sum(1 for r in results if r.status == "fail")
    avg = round(sum(r.score for r in scored) / len(scored), 3) if scored else 0.0

    summary = {
        "phase": "p2",
        "version": "2.0",
        "ide": ide,
        "ide_capabilities": sorted(ide_caps),
        "tester": meta.get("tester", ""),
        "date": meta.get("date", ""),
        "total": len(results),
        "passed": n_pass,
        "failed": n_fail,
        "incomplete": sum(1 for r in results if r.status == "incomplete"),
        "skipped_capability": sum(1 for r in results if r.status == "skipped_capability"),
        "avg_score": avg,
        "cases": [
            {
                "case_id": r.case_id,
                "status": r.status,
                "score": round(r.score, 3),
                "skip_reason": r.skip_reason,
                "fail_reason": r.fail_reason,
                "critical_failed": [d.key for d in r.critical_failed],
                "structure": _current_structure(r),
                "dims": [
                    {"turn": d.turn, "key": d.key, "tier": d.tier,
                     "status": d.status, "value": d.value}
                    for d in r.dims
                ],
            }
            for r in results
        ],
    }

    out_dir = Path(args.out_dir) if args.out_dir else results_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / f"summary.{ide or 'unknown'}.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    # Log the summary path to stderr so stdout stays clean for --format markdown
    print(f"summary → {summary_path}", file=sys.stderr)

    return 0 if n_fail == 0 and summary["incomplete"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
