"""Shared helpers for slice/scenario validation scripts.

This module is intentionally dependency-light:
    - PyYAML  (frontmatter parsing, index.yaml load)
    - stdlib  (everything else)

Conventions:
    - All scripts accept positional file paths and exit with code 0 on
      success, 1 on validation failure, 2 on usage error.
    - Errors are printed in a consistent format:
          {file}:{line?}: [{code}] {message}
      so they can be grepped, piped, and read by CI.
    - When a check has many sub-rules, every failure is printed before exit;
      we never bail on the first error within a single file.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

# ---- Repo discovery ---------------------------------------------------------

KB_DIR_NAME = "knowledge-base"


def repo_root(start: Path | None = None) -> Path:
    """Walk up from `start` (or this file) to find the repo containing knowledge-base/."""
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / KB_DIR_NAME).is_dir():
            return parent
    raise SystemExit(f"[fatal] cannot find knowledge-base/ from {here}")


def kb_dir() -> Path:
    return repo_root() / KB_DIR_NAME


# ---- Frontmatter parsing ----------------------------------------------------

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


@dataclass
class ParsedDoc:
    path: Path
    frontmatter: dict
    body: str
    body_offset: int  # line number where body starts (1-indexed)
    raw: str

    def line_of(self, char_offset_in_body: int) -> int:
        """Map a character offset in `body` back to a 1-indexed file line."""
        before = self.body[:char_offset_in_body]
        return self.body_offset + before.count("\n")


def parse_doc(path: Path) -> ParsedDoc:
    raw = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(raw)
    if not m:
        return ParsedDoc(path=path, frontmatter={}, body=raw, body_offset=1, raw=raw)
    fm_text = m.group(1)
    body = raw[m.end():]
    body_offset = raw[: m.end()].count("\n") + 1
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"{path}: invalid YAML frontmatter: {e}") from e
    if not isinstance(fm, dict):
        raise ValueError(f"{path}: frontmatter must be a mapping, got {type(fm).__name__}")
    return ParsedDoc(path=path, frontmatter=fm, body=body, body_offset=body_offset, raw=raw)


# ---- Section extraction -----------------------------------------------------

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$", re.MULTILINE)


@dataclass
class Section:
    level: int          # number of '#'
    title: str          # text after '#'s, stripped
    start: int          # offset in body where heading line starts
    body_start: int     # offset in body right after heading line
    end: int            # offset in body where the section ends (exclusive)

    @property
    def heading(self) -> str:
        return self.title


def iter_sections(body: str) -> list[Section]:
    matches = list(HEADING_RE.finditer(body))
    sections: list[Section] = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        body_start = m.end() + 1 if m.end() < len(body) and body[m.end()] == "\n" else m.end()
        # section ends at the next heading whose level <= this one
        end = len(body)
        for j in range(i + 1, len(matches)):
            if len(matches[j].group(1)) <= level:
                end = matches[j].start()
                break
        sections.append(Section(level=level, title=title, start=m.start(), body_start=body_start, end=end))
    return sections


def find_section(body: str, title_predicate) -> Section | None:
    """Find first section whose title matches the predicate (callable or string)."""
    if isinstance(title_predicate, str):
        target = title_predicate
        pred = lambda t: t == target or t.startswith(target + " ")
    else:
        pred = title_predicate
    for sec in iter_sections(body):
        if pred(sec.title):
            return sec
    return None


def section_text(body: str, sec: Section) -> str:
    return body[sec.body_start:sec.end]


# ---- Code block extraction --------------------------------------------------

# Matches ``` (with optional language hint) ... ``` blocks.
# Captures (lang, content). DOTALL so content can span lines.
CODE_FENCE_RE = re.compile(r"^```([^\n`]*)\n(.*?)^```\s*$", re.DOTALL | re.MULTILINE)


@dataclass
class CodeBlock:
    lang: str
    content: str
    start_offset: int  # offset in body
    end_offset: int


def iter_code_blocks(body: str) -> list[CodeBlock]:
    blocks = []
    for m in CODE_FENCE_RE.finditer(body):
        lang = m.group(1).strip()
        content = m.group(2)
        blocks.append(CodeBlock(lang=lang, content=content, start_offset=m.start(), end_offset=m.end()))
    return blocks


# ---- Index.yaml loading -----------------------------------------------------

_INDEX_CACHE: dict | None = None


def load_index() -> dict:
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        path = kb_dir() / "index.yaml"
        with path.open("r", encoding="utf-8") as f:
            _INDEX_CACHE = yaml.safe_load(f) or {}
    return _INDEX_CACHE


def index_slice_ids() -> set[str]:
    idx = load_index()
    return {s["id"] for s in (idx.get("slices") or []) if "id" in s}


def index_scenario_ids() -> set[str]:
    idx = load_index()
    return {s["id"] for s in (idx.get("scenarios") or []) if "id" in s}


def index_scenario_slices(scenario_id: str) -> list[str]:
    idx = load_index()
    for s in idx.get("scenarios") or []:
        if s.get("id") == scenario_id:
            return list(s.get("slices") or [])
    return []


# ---- Reporting --------------------------------------------------------------

@dataclass
class Report:
    file: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def err(self, code: str, msg: str, line: int | None = None) -> None:
        loc = f"{self.file}:{line}" if line else f"{self.file}"
        self.errors.append(f"{loc}: [{code}] {msg}")

    def warn(self, code: str, msg: str, line: int | None = None) -> None:
        loc = f"{self.file}:{line}" if line else f"{self.file}"
        self.warnings.append(f"{loc}: [{code}] {msg}")

    def print(self) -> None:
        for w in self.warnings:
            print(f"warning: {w}")
        for e in self.errors:
            print(f"error:   {e}")

    @property
    def ok(self) -> bool:
        return not self.errors


def collect_files(args: Iterable[str], default_glob: str | None = None) -> list[Path]:
    """Expand CLI args into a list of files. Directories are walked for .md."""
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            out.extend(sorted(p.rglob("*.md")))
        elif p.is_file():
            out.append(p)
        else:
            print(f"warning: path not found: {a}", file=sys.stderr)
    if not out and default_glob:
        out = sorted(kb_dir().rglob(default_glob))
    return out


def run_cli(check_one, default_glob: str = "*.md") -> int:
    """Standard CLI loop: parse argv -> call check_one(path) -> aggregate.

    `check_one(path: Path) -> Report`
    """
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <file_or_dir> [...]", file=sys.stderr)
        return 2
    files = collect_files(sys.argv[1:], default_glob=default_glob)
    if not files:
        print("no files matched", file=sys.stderr)
        return 2
    failed = 0
    for f in files:
        try:
            rep = check_one(f)
        except Exception as e:  # noqa: BLE001
            rep = Report(file=f)
            rep.err("EXCEPTION", f"{type(e).__name__}: {e}")
        rep.print()
        if not rep.ok:
            failed += 1
    print(f"\n=== {len(files)} file(s) checked, {failed} failed ===")
    return 0 if failed == 0 else 1
