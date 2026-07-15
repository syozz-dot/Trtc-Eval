"""conference/web apply checks.

Invoked by the shared tools/apply.py plugin dispatcher when product=conference.

Interface contract (required by the dispatcher):

    build_checks(target_id, slice_ids, project_root, platform)
        -> (status: str, shared_checks: list[dict], debug: dict)

All logic here is conference + Vue/TS specific:
  - src/ layout scanning (.vue / .ts)
  - JS/TS comment and string literal stripping (anti-cheat)
  - composable entry-symbol presence check
  - duplicate-declaration detection (JS const/let/var)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# rule_parser — conference entry-symbol map
# ---------------------------------------------------------------------------
_VERIFY_LIB_DIR = Path(__file__).resolve().parents[1] / "verify_lib"
_RULE_PARSER_IMPORT_ERROR: Exception | None = None

try:
    sys.path.insert(0, str(_VERIFY_LIB_DIR))
    from rule_parser import entry_symbols_for_slice
except ImportError as exc:  # pragma: no cover
    entry_symbols_for_slice = None  # type: ignore[assignment]
    _RULE_PARSER_IMPORT_ERROR = exc
finally:
    try:
        sys.path.remove(str(_VERIFY_LIB_DIR))
    except ValueError:  # pragma: no cover
        pass


# ---------------------------------------------------------------------------
# JS / TS source scanning
# ---------------------------------------------------------------------------

def _strip_comments_and_strings(content: str) -> str:
    """Strip JS/TS comments and string literals to prevent anti-cheat symbol stuffing."""
    out: list[str] = []
    i = 0
    n = len(content)
    while i < n:
        if content[i:i + 2] == "//":
            end = content.find("\n", i)
            if end == -1:
                end = n
            out.append(" " * (end - i))
            i = end
        elif content[i:i + 2] == "/*":
            end = content.find("*/", i + 2)
            if end == -1:
                end = n
            else:
                end += 2
            replaced = content[i:end]
            out.append(re.sub(r"[^\n]", " ", replaced))
            i = end
        elif content[i] == '"':
            j = i + 1
            while j < n:
                if content[j] == "\\" and j + 1 < n:
                    j += 2
                elif content[j] == '"':
                    j += 1
                    break
                else:
                    j += 1
            out.append('""' + " " * max(0, j - i - 2))
            i = j
        elif content[i] == "'":
            j = i + 1
            while j < n:
                if content[j] == "\\" and j + 1 < n:
                    j += 2
                elif content[j] == "'":
                    j += 1
                    break
                else:
                    j += 1
            out.append("''" + " " * max(0, j - i - 2))
            i = j
        elif content[i] == "`":
            j = i + 1
            while j < n:
                if content[j] == "\\" and j + 1 < n:
                    j += 2
                elif content[j] == "`":
                    j += 1
                    break
                else:
                    j += 1
            out.append("``" + " " * max(0, j - i - 2))
            i = j
        else:
            out.append(content[i])
            i += 1
    return "".join(out)


def _scan_project_src(project_root: Path) -> tuple[str, list[tuple[Path, str]]]:
    """Scan the standard Vite/Vue CLI src/ layout for .vue and .ts source files."""
    src = project_root / "src"
    if not src.exists():
        return "static-only", []
    files: list[tuple[Path, str]] = []
    for ext in ("*.vue", "*.ts"):
        for file_path in src.rglob(ext):
            try:
                raw = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            files.append((file_path, _strip_comments_and_strings(raw)))
    return ("full" if files else "static-only", files)


# ---------------------------------------------------------------------------
# Entry-symbol presence check (conference composables)
# ---------------------------------------------------------------------------

def _check_slice_entry(slice_id: str, files: list[tuple[Path, str]]) -> tuple[str, list[str]]:
    """Return ('passed'|'failed'|'skipped', entry_symbols).

    Passes when any one of the registered entry symbols for the slice is
    found as a real code identifier (comments/strings already stripped).
    'skipped' means no entry symbol is registered for this slice.
    """
    if entry_symbols_for_slice is None:
        return "skipped", []
    symbols = entry_symbols_for_slice(slice_id)
    if not symbols:
        return "skipped", []
    for symbol in symbols:
        pattern = re.compile(r"\b" + re.escape(symbol) + r"\b")
        for _path, content in files:
            if pattern.search(content):
                return "passed", symbols
    return "failed", symbols


# ---------------------------------------------------------------------------
# Duplicate-declaration check (JS/TS const/let/var)
# ---------------------------------------------------------------------------

_IDENT = r"[A-Za-z_$][\w$]*"
_SIMPLE_DECL_RE = re.compile(
    r"\b(?:const|let|var)\s+(" + _IDENT + r")\s*[=:]"
    r"|\b(?:async\s+)?function\s*\*?\s*(" + _IDENT + r")"
    r"|\bclass\s+(" + _IDENT + r")"
)
_DESTRUCTURE_RE = re.compile(r"\b(?:const|let|var)\s*\{([^{}]*)\}\s*=\s*([^\n;]*)")


def _destructured_binding_names(brace_body: str) -> list[str]:
    names: list[str] = []
    for part in brace_body.split(","):
        part = part.strip()
        if not part or "{" in part:
            continue
        if part.startswith("..."):
            part = part[3:].strip()
        if ":" in part:
            part = part.split(":", 1)[1]
        part = part.split("=", 1)[0].strip()
        if re.fullmatch(_IDENT, part):
            names.append(part)
    return names


def _check_duplicate_declarations(files: list[tuple[Path, str]], project_root: Path) -> list[dict]:
    issues: list[dict] = []
    for path, content in files:
        destructured: list[str] = []
        for match in _DESTRUCTURE_RE.finditer(content):
            brace_body, rhs = match.group(1), match.group(2)
            if "(" not in rhs:
                continue
            destructured.extend(_destructured_binding_names(brace_body))
        simple: list[str] = []
        for match in _SIMPLE_DECL_RE.finditer(content):
            name = match.group(1) or match.group(2) or match.group(3)
            if name:
                simple.append(name)
        try:
            rel = str(path.resolve().relative_to(project_root.resolve()))
        except (ValueError, OSError):
            rel = str(path)
        for name in sorted(set(destructured)):
            destructure_count = destructured.count(name)
            simple_count = simple.count(name)
            if destructure_count >= 2 or (destructure_count >= 1 and simple_count >= 1):
                issues.append(
                    {
                        "symbol": name,
                        "file": rel,
                        "summary": (
                            f"duplicate declaration '{name}' in {rel}: destructured from a composable "
                            f"and re-declared in the same file ({destructure_count} destructure, "
                            f"{simple_count} const/function/class)"
                        ),
                    }
                )
    return issues


# ---------------------------------------------------------------------------
# Orchestration — public interface for the dispatcher
# ---------------------------------------------------------------------------

def _run_checks(
    target_id: str,
    slice_ids: list[str],
    project_root: Path,
    project_files: list[tuple[Path, str]],
    mode: str,
) -> tuple[str, list[dict], dict]:
    shared_checks: list[dict] = []
    debug_slice_results: list[dict] = []
    issues: list[dict] = []
    failed = False

    if mode == "static-only":
        failed = True
        check = {
            "id": "source_files_present",
            "status": "failed",
            "summary": "no .vue/.ts source files were found under src/",
        }
        shared_checks.append(check)
        issues.append({"type": "source", "rule_text": check["summary"]})
    else:
        shared_checks.append(
            {
                "id": "source_files_present",
                "status": "passed",
                "summary": f"found {len(project_files)} .vue/.ts source file(s) under src/",
            }
        )

    for slice_id in slice_ids:
        entry_status, entry_symbols = _check_slice_entry(slice_id, project_files)
        debug_slice_results.append(
            {
                "slice_id": slice_id,
                "entry_result": entry_status,
                "entry_symbols": entry_symbols,
            }
        )
        if entry_status == "skipped":
            continue
        if entry_status == "passed":
            shared_checks.append(
                {
                    "id": "entry_symbol_present",
                    "status": "passed",
                    "slice_id": slice_id,
                    "summary": f"entry symbol for '{slice_id}' was found in user code",
                }
            )
            continue
        failed = True
        check = {
            "id": "entry_symbol_present",
            "status": "failed",
            "slice_id": slice_id,
            "summary": (
                f"entry symbol for '{slice_id}' was not found in user code"
                + (f" ({', '.join(entry_symbols)})" if entry_symbols else "")
            ),
        }
        shared_checks.append(check)
        issues.append({"type": "entry", "slice_id": slice_id, "rule_text": check["summary"]})

    for issue in _check_duplicate_declarations(project_files, project_root):
        failed = True
        check = {
            "id": "duplicate_declaration",
            "status": "failed",
            "summary": issue["summary"],
            "file": issue["file"],
            "symbol": issue["symbol"],
        }
        shared_checks.append(check)
        issues.append(
            {
                "type": "duplicate-declaration",
                "slice_id": target_id,
                "rule_text": issue["summary"],
                "file": issue["file"],
                "symbol": issue["symbol"],
            }
        )

    debug = {
        "target_id": target_id,
        "files_scanned": len(project_files),
        "mode": mode,
        "slice_results": debug_slice_results,
        "issues": issues,
    }
    return ("failed" if failed else "passed"), shared_checks, debug


def build_checks(
    target_id: str,
    slice_ids: list[str],
    project_root: Path,
    platform: str,  # noqa: ARG001 — reserved for future per-platform branching
) -> tuple[str, list[dict], dict]:
    """Entry point for the shared apply.py plugin dispatcher.

    platform is accepted but currently unused — all conference slices are
    web/Vue, so the same checks apply regardless. Kept in the signature for
    forward-compatibility (e.g. future conference/electron or conference/mobile).

    If rule_parser failed to import, entry-symbol checks are skipped (reported
    as 'skipped' per-slice). source_files_present and duplicate_declaration
    checks still run — those do not depend on rule_parser.
    """
    mode, project_files = _scan_project_src(project_root)
    return _run_checks(target_id, slice_ids, project_root, project_files, mode)
