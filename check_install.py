#!/usr/bin/env python3
"""
check_install.py — Phase 1: Install & adapter checks for each IDE.

读取 cases.json v2 的 asset_catalog + ide_profiles + P1 cases，按 IDE 检查全量资产。
每个 IDE 的资产清单从 ide_profiles[ide].asset_groups 引用 asset_catalog 中的资产组得到，
避免在每条 case 里重复硬编码路径。

Usage:
    python3 check_install.py [--repo-root PATH] [--ide claude-code|cursor|codebuddy|codex|all]
    python3 check_install.py --repo-root ~/path/to/agent-skills --ide all

Exit codes:
    0  all checks passed
    1  one or more checks failed
    2  usage / config error
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent


# ── helpers ──────────────────────────────────────────────────────────────────

def find_repo_root(hint: Optional[str]) -> Path:
    if hint:
        p = Path(hint).expanduser().resolve()
        if not p.exists():
            sys.exit(f"[check_install] repo-root not found: {hint}")
        return p
    # try cwd — 在评测目录下应该能看到 .claude/skills/trtc/SKILL.md（npx add 后）
    cwd = Path.cwd()
    if any((cwd / ide / "skills" / "trtc" / "SKILL.md").exists()
           for ide in [".claude", ".cursor", ".codebuddy", ".codex"]):
        return cwd
    sys.exit(
        "[check_install] Cannot auto-detect repo root.\n"
        "  Expected .claude/ / .cursor/ / .codebuddy/ / .codex/ in current dir.\n"
        "  Run `npx -y @tencent-rtc/trtc-agent-skills@latest add` first,\n"
        "  or pass --repo-root <path>"
    )


def run_command(cmd: str, cwd: Path) -> tuple[int, str]:
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=15
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"
    except Exception as e:
        return 1, str(e)


# ── result types ─────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    asset_group: str
    description: str
    passed: bool
    detail: str = ""


@dataclass
class CaseResult:
    case_id: str
    ide: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


# ── core runner ───────────────────────────────────────────────────────────────

def check_asset_group(
    group_name: str,
    group_def: dict,
    repo_root: Path,
    install_prefix: str,
) -> CheckResult:
    """Check that all files in an asset group exist + run any executable_check.
    All paths are resolved as: repo_root / install_prefix / rel
    """
    desc = group_def.get("description", group_name)
    files = group_def.get("files", [])

    prefix_path = repo_root / install_prefix if install_prefix else repo_root
    missing = [rel for rel in files if not (prefix_path / rel).exists()]
    if missing:
        return CheckResult(
            asset_group=group_name,
            description=desc,
            passed=False,
            detail=f"Missing {len(missing)}/{len(files)}: " + ", ".join(missing[:3]) +
                   ("" if len(missing) <= 3 else f" (+{len(missing)-3} more)")
        )

    # all files exist — run executable checks if any
    for ec in group_def.get("executable_check", []):
        cmd = ec["command"]
        expected = ec.get("expect_exit_code", 0)
        code, output = run_command(cmd, cwd=prefix_path)
        if code != expected:
            return CheckResult(
                asset_group=group_name,
                description=desc,
                passed=False,
                detail=f"`{cmd}` failed: exit={code}, output={output[:200]}"
            )

    return CheckResult(
        asset_group=group_name,
        description=desc,
        passed=True,
        detail=f"{len(files)} file(s) ✓"
    )


def run_p1_case(case: dict, asset_catalog: dict, ide_profiles: dict, repo_root: Path) -> CaseResult:
    ide = case.get("ide", "unknown")
    result = CaseResult(case_id=case["case_id"], ide=ide)

    profile = ide_profiles.get(ide)
    if not profile:
        result.checks.append(CheckResult(
            asset_group="<profile>",
            description=f"IDE profile not found: {ide}",
            passed=False,
            detail="Add an entry under ide_profiles in cases.json"
        ))
        return result

    install_prefix = profile.get("install_root_prefix", "")
    asset_groups = profile.get("asset_groups", [])
    if not asset_groups:
        result.checks.append(CheckResult(
            asset_group="<profile>",
            description=f"No asset_groups configured for {ide}",
            passed=False,
        ))
        return result

    for group_name in asset_groups:
        group_def = asset_catalog.get(group_name)
        if not group_def:
            result.checks.append(CheckResult(
                asset_group=group_name,
                description=f"Asset group missing in catalog: {group_name}",
                passed=False,
            ))
            continue
        result.checks.append(check_asset_group(group_name, group_def, repo_root, install_prefix))

    return result


# ── reporting ─────────────────────────────────────────────────────────────────

def print_table(case_results: list[CaseResult]) -> None:
    """Human-readable table to stderr."""
    use_color = sys.stderr.isatty()
    YEL = "\033[33m" if use_color else ""
    DIM = "\033[2m" if use_color else ""
    RST = "\033[0m" if use_color else ""

    WIDTH = 76
    print(f"\n{'─' * WIDTH}", file=sys.stderr)
    print("  Phase 1 · Install Check Results", file=sys.stderr)
    print(f"{'─' * WIDTH}", file=sys.stderr)

    for cr in case_results:
        icon = "✓" if cr.passed else "✗"
        passed_n = sum(1 for c in cr.checks if c.passed)
        total = len(cr.checks)
        print(f"\n  [{icon}] {cr.case_id}  (IDE: {cr.ide})  {passed_n}/{total} groups", file=sys.stderr)
        for chk in cr.checks:
            sub_icon = "  ✓" if chk.passed else "  ✗"
            print(f"     {sub_icon}  {chk.asset_group:<28} {chk.description}", file=sys.stderr)
            if chk.detail:
                color = YEL if not chk.passed else DIM
                print(f"          {color}→ {chk.detail}{RST}", file=sys.stderr)

    total = len(case_results)
    passed = sum(1 for c in case_results if c.passed)
    print(f"\n{'─' * WIDTH}", file=sys.stderr)
    print(f"  Result: {passed}/{total} cases passed", file=sys.stderr)
    print(f"{'─' * WIDTH}\n", file=sys.stderr)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1 install checker")
    parser.add_argument("--repo-root", help="Path to agent-skills repo (auto-detected if cwd has skills/trtc/SKILL.md)")
    parser.add_argument("--ide", default="all", help="IDE filter: claude-code|cursor|codebuddy|codex|all")
    parser.add_argument("--cases", help="Path to cases.json (default: sibling cases.json)")
    parser.add_argument("--json-out", help="Write JSON summary to this file instead of stdout")
    args = parser.parse_args()

    cases_path = Path(args.cases) if args.cases else HERE / "cases.json"
    if not cases_path.exists():
        sys.exit(f"[check_install] cases.json not found: {cases_path}")

    with open(cases_path) as f:
        data = json.load(f)

    if data.get("version", "").startswith("1."):
        sys.exit(
            f"[check_install] cases.json is v{data['version']} (old format).\n"
            f"  Expected v2.0.0+ with asset_catalog + ide_profiles."
        )

    asset_catalog = data.get("asset_catalog", {})
    ide_profiles = data.get("ide_profiles", {})
    if not asset_catalog or not ide_profiles:
        sys.exit("[check_install] cases.json missing asset_catalog or ide_profiles")

    repo_root = find_repo_root(args.repo_root)

    p1_cases = [
        c for c in data["cases"]
        if c.get("phase") == "p1"
        and (args.ide == "all" or c.get("ide") == args.ide)
    ]

    if not p1_cases:
        print(json.dumps({"status": "no_cases", "ide_filter": args.ide}))
        return 0

    print(f"[check_install] repo-root: {repo_root}", file=sys.stderr)
    print(f"[check_install] running {len(p1_cases)} P1 case(s) for IDE: {args.ide}", file=sys.stderr)

    results = [run_p1_case(c, asset_catalog, ide_profiles, repo_root) for c in p1_cases]
    print_table(results)

    summary = {
        "phase": "p1",
        "version": data.get("version"),
        "repo_root": str(repo_root),
        "ide_filter": args.ide,
        "total": len(results),
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(1 for r in results if not r.passed),
        "cases": [
            {
                "case_id": r.case_id,
                "ide": r.ide,
                "passed": r.passed,
                "checks": [
                    {
                        "asset_group": c.asset_group,
                        "passed": c.passed,
                        "detail": c.detail,
                    }
                    for c in r.checks
                ],
            }
            for r in results
        ],
    }

    output = json.dumps(summary, indent=2, ensure_ascii=False)
    if args.json_out:
        Path(args.json_out).write_text(output)
        print(f"[check_install] Summary written to {args.json_out}", file=sys.stderr)
    else:
        print(output)

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
