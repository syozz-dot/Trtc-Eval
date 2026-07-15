#!/usr/bin/env python3
"""Render stable agent entry stubs for the TRTC dispatcher.

Phase 4 target state: agent entry files stay short and point to the shared
root dispatcher instead of duplicating product-specific runtime rules.
"""
import argparse
import sys
from pathlib import Path

STUB = """# TRTC AI Integration

Reply in the user's language.

For any TRTC-related request, read and follow `skills/trtc/SKILL.md` first.
Do not answer from training data. Do not skip the dispatcher or any routed owner skill.
"""

CURSOR_STUB = """---
alwaysApply: true
---

# TRTC AI Integration

Reply in the user's language.

For any TRTC-related request, read and follow `skills/trtc/SKILL.md` first.
Do not answer from training data. Do not skip the dispatcher or any routed owner skill.
"""

TARGETS = {
    "AGENTS.md": STUB,
    "CLAUDE.md": STUB,
    "CODEBUDDY.md": STUB,
    ".cursor/rules/main.mdc": CURSOR_STUB,
}

LEGACY_TARGETS = (
    ".cursor/rules/ui-mode.mdc",
)


def _stale_targets(project_root: Path) -> list[str]:
    stale: list[str] = []
    for rel, expected in TARGETS.items():
        path = project_root / rel
        actual = path.read_text() if path.exists() else None
        if actual != expected:
            stale.append(rel)
    for rel in LEGACY_TARGETS:
        if (project_root / rel).exists():
            stale.append(rel)
    return stale


def _render(project_root: Path) -> None:
    for rel, body in TARGETS.items():
        path = project_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    for rel in LEGACY_TARGETS:
        path = project_root / rel
        if path.exists():
            path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Render stable TRTC agent entry stubs.")
    parser.add_argument("--project-root", default=".", help="Repo root (defaults to CWD)")
    parser.add_argument("--check", action="store_true", help="Exit 2 if entry files are stale")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()

    if args.check:
        stale = _stale_targets(root)
        if stale:
            print("render_ai_instructions: stale entry targets:", file=sys.stderr)
            for rel in stale:
                print(f"  {rel}", file=sys.stderr)
            print(
                "Re-run `python3 skills/trtc/tools/entry/render_ai_instructions.py` and commit the diff.",
                file=sys.stderr,
            )
            return 2
        return 0

    _render(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
