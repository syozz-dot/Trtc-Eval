"""TRTC knowledge-base path resolver.

Resolves logical paths under ``knowledge-base/`` relative to the install root
(``knowledge-base/`` sibling of ``skills/``). Used by domain skills so agents
never hard-code ``../`` depth to reach the KB.

Usage (cwd = ``skills/trtc`` or ``skills/trtc-chat``; latter uses a shim in
``trtc-chat/tools/`` that delegates here):

  python3 -m tools.kb resolve chat/web/index.yaml
  python3 -m tools.kb resolve slices/chat/web/login-auth.md
  python3 -m tools.kb read docs/chat/gen-usersig.md
  python3 -m tools.kb exists chat/web/index.yaml

Environment:
  TRTC_REPO_ROOT  Optional override for repo / plugin install root.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

THIS_FILE = Path(__file__).resolve()
DEFAULT_REPO_ROOT = THIS_FILE.parent.parent.parent.parent
ENV_REPO_ROOT = "TRTC_REPO_ROOT"
KB_DIR_NAME = "knowledge-base"


class KBError(Exception):
    """KB resolver error."""


def repo_root() -> Path:
    env = os.environ.get(ENV_REPO_ROOT)
    return Path(env).resolve() if env else DEFAULT_REPO_ROOT


def kb_root() -> Path:
    return repo_root() / KB_DIR_NAME


def normalize_relpath(raw: str) -> str:
    text = raw.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    text = text.lstrip("/")
    prefix = f"{KB_DIR_NAME}/"
    if text.startswith(prefix):
        text = text[len(prefix) :]
    if not text:
        raise KBError("KB relative path must be non-empty")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise KBError("KB relative path must not contain '..'")
    return "/".join(parts)


def resolve_path(relpath: str) -> Path:
    rel = normalize_relpath(relpath)
    root = kb_root().resolve()
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise KBError(f"path escapes knowledge-base root: {relpath}") from exc
    return target


def cmd_resolve(relpath: str) -> int:
    try:
        target = resolve_path(relpath)
    except KBError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not target.exists():
        print(f"ERROR: not found: {target}", file=sys.stderr)
        return 1
    print(str(target))
    return 0


def cmd_read(relpath: str) -> int:
    try:
        target = resolve_path(relpath)
    except KBError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not target.is_file():
        print(f"ERROR: not a file: {target}", file=sys.stderr)
        return 1
    sys.stdout.write(target.read_text(encoding="utf-8"))
    return 0


def cmd_exists(relpath: str) -> int:
    try:
        target = resolve_path(relpath)
    except KBError:
        return 1
    return 0 if target.exists() else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve TRTC knowledge-base paths.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    resolve = sub.add_parser("resolve", help="Print absolute path under knowledge-base/")
    resolve.add_argument("relpath", help="Path inside knowledge-base/, e.g. chat/web/index.yaml")

    read = sub.add_parser("read", help="Print file contents (UTF-8 text files only)")
    read.add_argument("relpath", help="File path inside knowledge-base/")

    exists = sub.add_parser("exists", help="Exit 0 if path exists, 1 otherwise")
    exists.add_argument("relpath", help="Path inside knowledge-base/")

    args = parser.parse_args(argv)
    if args.cmd == "resolve":
        return cmd_resolve(args.relpath)
    if args.cmd == "read":
        return cmd_read(args.relpath)
    if args.cmd == "exists":
        return cmd_exists(args.relpath)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
