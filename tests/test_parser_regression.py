#!/usr/bin/env python3
"""Golden-fixture regression for run_eval.py parsers + judges.

Loads pre-captured stream-json transcripts from fixtures/transcripts/<ide>/<case>.turn1.jsonl,
re-runs parse_transcript() + observation judges against the case's expect block,
and asserts every observation returns Y.

Any N here means either (a) a parser dialect regressed, or (b) a judge got stricter
in a way that would silently break past-known-good behavior. Both are things we want
to catch before merge, since neither trips the runtime CLI itself.

Run standalone:
    python3 tests/test_parser_regression.py

Exits non-zero on any failure. No pytest dependency (CI has stdlib only).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

from run_eval import (  # noqa: E402
    parse_transcript,
    _match_route_level1,
    _match_reporting_call,
    _match_tools_called,
    _match_route_triggered,
)


FIXTURES_DIR = REPO / "fixtures" / "transcripts"
CASES_JSON = REPO / "cases.json"

IDE_DIALECT = {
    "claude-code": "claude",
    "codex":       "codex",
    "cursor":      "cursor",
    "codebuddy":   "claude",
}


def load_cases() -> dict:
    data = json.loads(CASES_JSON.read_text())
    return {c["case_id"]: c for c in data["cases"] if "case_id" in c}


def check_case(ide: str, case_id: str, cases: dict) -> list[str]:
    """Return list of failure messages (empty = all Y)."""
    dialect = IDE_DIALECT[ide]
    path = FIXTURES_DIR / ide / f"{case_id}.turn1.jsonl"
    if not path.exists():
        return [f"missing fixture: {path.relative_to(REPO)}"]

    case = cases[case_id]
    turn = case["turns"][0]
    expect = turn["expect"]

    tr = parse_transcript(path.read_text(), dialect=dialect)

    if not tr.tool_calls:
        return [f"parser returned 0 tool_calls (dialect={dialect}); "
                f"raw stream-json had events but parser did not pick them up"]

    failures: list[str] = []

    if "route_level1" in expect:
        rl1 = expect["route_level1"]
        ok, msg = _match_route_level1(tr, rl1.get("target", ""), rl1.get("must_not", []))
        if not ok:
            failures.append(f"route_level1: {msg}")

    if "reporting_called" in expect:
        scripts = expect["reporting_called"].get("scripts", [])
        ok, msg = _match_reporting_call(tr.bash_commands, scripts)
        if not ok:
            failures.append(f"reporting_called: {msg}")

    if "tools_called" in expect:
        ok, msg = _match_tools_called(tr, expect["tools_called"])
        if not ok:
            failures.append(f"tools_called: {msg}")

    if "route_triggered" in expect:
        ok, msg = _match_route_triggered(tr, expect["route_triggered"])
        if not ok:
            failures.append(f"route_triggered: {msg}")

    return failures


def main() -> int:
    cases = load_cases()
    all_failures: list[tuple[str, str, list[str]]] = []
    checked = 0
    for ide_dir in sorted(FIXTURES_DIR.iterdir()):
        if not ide_dir.is_dir():
            continue
        ide = ide_dir.name
        if ide not in IDE_DIALECT:
            print(f"[warn] unknown IDE fixture dir: {ide} (skipped)")
            continue
        for fixture in sorted(ide_dir.glob("*.turn1.jsonl")):
            case_id = fixture.name.replace(".turn1.jsonl", "")
            if case_id not in cases:
                print(f"[warn] fixture {ide}/{case_id} has no matching case in cases.json (skipped)")
                continue
            failures = check_case(ide, case_id, cases)
            checked += 1
            if failures:
                all_failures.append((ide, case_id, failures))
                for f in failures:
                    print(f"  FAIL  {ide:12s}  {case_id:20s}  {f}")
            else:
                print(f"  ok    {ide:12s}  {case_id}")

    print()
    print(f"checked {checked} fixture(s); {len(all_failures)} failure(s)")
    return 1 if all_failures else 0


if __name__ == "__main__":
    sys.exit(main())
