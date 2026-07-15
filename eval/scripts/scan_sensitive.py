#!/usr/bin/env python3
"""Sensitive-info scanner for Trtc-Eval repo.

Scans committed/staged content for API keys, tokens, and PII patterns that
should never leave a developer machine. Used in two places:

  1. pre-commit hook — scans the diff about to be committed. `--staged`.
  2. CI workflow    — scans the full tree of a PR checkout. no flag.

Exits non-zero on any hit and prints file/line/pattern. Zero external deps.

Rules are intentionally simple substring + regex; false positives get added
to ALLOWED_LITERALS below (e.g. example strings in docs) rather than making
the regex smarter.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


PATTERNS: list[tuple[str, str]] = [
    # Anthropic API keys / OAuth tokens
    ("anthropic-api-key",   r"\bsk-ant-[a-zA-Z0-9_-]{20,}"),
    ("anthropic-oauth",     r"\bsk-ant-oat[0-9]{2}-[a-zA-Z0-9_-]{20,}"),
    # OpenAI keys (legacy + project-scoped + service-account)
    ("openai-key",          r"\bsk-(?:proj-|svcacct-)?[a-zA-Z0-9_-]{20,}"),
    # GitHub tokens
    ("github-pat",          r"\bghp_[a-zA-Z0-9]{30,}"),
    ("github-oauth",        r"\bgho_[a-zA-Z0-9]{30,}"),
    ("github-app",          r"\b(?:ghs|ghu)_[a-zA-Z0-9]{30,}"),
    ("github-fine-grained", r"\bgithub_pat_[a-zA-Z0-9_]{50,}"),
    # AWS
    ("aws-access-key",      r"\bAKIA[0-9A-Z]{16}\b"),
    # Google
    ("google-api-key",      r"\bAIza[0-9A-Za-z_-]{35}\b"),
    # Slack
    ("slack-token",         r"\bxox[baprs]-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{20,}"),
    # Generic bearer / authorization headers with a token payload
    ("bearer-token",        r"[Bb]earer\s+[a-zA-Z0-9_.-]{20,}"),
    # Cursor / CodeBuddy CLI keys (guessed prefixes — refine if false-positive noisy)
    ("cursor-api-key",      r"\bcursor_[a-zA-Z0-9_-]{20,}"),
    # PII: email addresses (loose; ok because we only expect script identifiers here)
    ("email",               r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"),
    # PII: CN mobile numbers (13/14/15/16/17/18/19 prefix)
    ("cn-mobile",           r"(?<!\d)1[3-9]\d{9}(?!\d)"),
]


# Literals that trip a pattern but are known-safe (test data, doc examples).
# Match on the ENTIRE matched string. Case-sensitive.
ALLOWED_LITERALS: set[str] = {
    "noreply@anthropic.com",
    "example@example.com",
    "user@example.com",
    # add here when confirmed benign
}


# File extensions to scan. Binaries and generated artifacts skipped.
SCAN_EXTS = {
    ".py", ".js", ".ts", ".sh", ".yml", ".yaml", ".json", ".jsonl",
    ".md", ".html", ".txt", ".env", ".cfg", ".ini", ".toml",
}

# Directories always skipped
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache"}


def is_allowed(match_text: str) -> bool:
    return match_text in ALLOWED_LITERALS


def list_staged_files() -> list[Path]:
    """Files added/modified in the git index. Deleted files excluded."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=REPO, capture_output=True, text=True, check=True,
    )
    return [REPO / line for line in result.stdout.splitlines() if line.strip()]


def walk_tree() -> list[Path]:
    """All scannable files in the working tree."""
    out: list[Path] = []
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        # skip if any parent is in SKIP_DIRS
        parts = set(path.relative_to(REPO).parts)
        if parts & SKIP_DIRS:
            continue
        if path.suffix in SCAN_EXTS:
            out.append(path)
    return out


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return list of (line_no, pattern_name, match_text)."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return []

    hits: list[tuple[int, str, str]] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for name, pattern in PATTERNS:
            for m in re.finditer(pattern, line):
                match_text = m.group(0)
                if is_allowed(match_text):
                    continue
                hits.append((line_no, name, match_text))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true",
                        help="scan only files staged in git index (pre-commit mode)")
    parser.add_argument("--paths", nargs="*", default=None,
                        help="scan only these paths (overrides other selection)")
    args = parser.parse_args()

    if args.paths:
        files = [Path(p).resolve() for p in args.paths if Path(p).is_file()]
    elif args.staged:
        files = list_staged_files()
    else:
        files = walk_tree()

    total_hits = 0
    for path in files:
        try:
            rel = path.relative_to(REPO)
        except ValueError:
            rel = path
        if path.suffix not in SCAN_EXTS:
            continue
        for line_no, name, match_text in scan_file(path):
            # Redact match beyond first 8 chars in output
            redacted = match_text[:8] + "…" if len(match_text) > 12 else match_text
            print(f"  {rel}:{line_no}  [{name}]  {redacted}")
            total_hits += 1

    if total_hits:
        print()
        print(f"❌ {total_hits} sensitive pattern(s) matched across {len(files)} scanned file(s).")
        print("   Fix the file(s) above or add benign matches to ALLOWED_LITERALS "
              "in scripts/scan_sensitive.py.")
        return 1

    print(f"✓ scanned {len(files)} file(s), no sensitive patterns matched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
