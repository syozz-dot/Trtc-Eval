"""Eval-side hook activator.

Two responsibilities:

  1. **Inject** a PostToolUse hook into `<working_dir>/.claude/settings.json`
     that points at `phase3/trace_posttooluse.py`, so every Read/Write/Edit/
     Bash tool call by the Claude Code CLI emits a `tool_call` trace event
     into `~/.cache/trtc-traces/<trtc-session>.jsonl`.

  2. **Restore** the original settings.json (via atexit) when the eval
     process exits. If the file didn't exist beforehand, delete our version.

The hook script is never distributed to end users. It lives in Trtc-Eval only.
When an eval run finishes, we also archive the produced trace files into
`eval-runs/<out_dir>/traces/<trtc-session>.jsonl` alongside the transcripts.

Concurrency note: settings.json write is protected by rename+atexit but
concurrent eval_runner processes on the same working_dir would race on the
backup file — do not run multiple `run_eval.py --with-trace` targeting the
same working_dir simultaneously.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOOK_SCRIPT = HERE / "trace_posttooluse.py"

# Match key for our hook so restore can pick it out precisely.
HOOK_MARKER_COMMAND = str(HOOK_SCRIPT)


def _settings_path(working_dir: Path) -> Path:
    return working_dir / ".claude" / "settings.json"


def _backup_path(settings: Path) -> Path:
    return settings.with_suffix(settings.suffix + ".trtc-eval-bak")


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text() or "{}")
    except Exception:
        # Malformed settings.json — do not clobber, let caller decide.
        raise RuntimeError(
            f"{path} is not valid JSON. Refusing to inject hook. "
            "Fix or move the file, then retry."
        )


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _hook_entry() -> dict:
    """Claude Code hook config entry — PostToolUse matcher for the 4 tools
    we care about. Bash exit≠0 will not trigger (schema §2.6 note); Read/
    Write/Edit fire unconditionally."""
    return {
        "matcher": "Read|Write|Edit|Bash",
        "hooks": [
            {
                "type": "command",
                "command": HOOK_MARKER_COMMAND,
            }
        ],
    }


def inject(working_dir: Path) -> None:
    """Register the PostToolUse hook. Backs up the existing settings.json
    verbatim so restore() is a plain file replace."""
    settings = _settings_path(working_dir)
    bak = _backup_path(settings)

    # Preserve original once — never overwrite a valid backup.
    if settings.exists() and not bak.exists():
        shutil.copy2(settings, bak)

    data = _load(settings)
    hooks = data.setdefault("hooks", {})
    ptu = hooks.setdefault("PostToolUse", [])

    # Idempotent: only add if our exact entry isn't already there.
    already = any(
        any(h.get("command") == HOOK_MARKER_COMMAND for h in entry.get("hooks", []))
        for entry in ptu
        if isinstance(entry, dict)
    )
    if not already:
        ptu.append(_hook_entry())
        _save(settings, data)

    # atexit fires on normal exits + uncaught exceptions, NOT on SIGKILL.
    atexit.register(_restore_once, working_dir)


_restored = False


def _restore_once(working_dir: Path) -> None:
    global _restored
    if _restored:
        return
    _restored = True
    restore(working_dir)


def restore(working_dir: Path) -> None:
    """Undo inject(). Prefer restoring from the backup; if no backup exists
    (meaning settings.json didn't exist before), delete our injected file
    entirely."""
    settings = _settings_path(working_dir)
    bak = _backup_path(settings)

    if bak.exists():
        shutil.move(str(bak), str(settings))
        return

    # No backup means we created settings.json from scratch. Remove it if it
    # only contains our injection; otherwise strip just our entry.
    if not settings.exists():
        return
    try:
        data = json.loads(settings.read_text() or "{}")
    except Exception:
        return

    hooks = data.get("hooks", {})
    ptu = hooks.get("PostToolUse", [])
    filtered = []
    for entry in ptu:
        if not isinstance(entry, dict):
            filtered.append(entry)
            continue
        inner = entry.get("hooks", [])
        remaining = [h for h in inner if h.get("command") != HOOK_MARKER_COMMAND]
        if remaining:
            entry["hooks"] = remaining
            filtered.append(entry)

    if filtered:
        hooks["PostToolUse"] = filtered
    else:
        hooks.pop("PostToolUse", None)

    if not hooks:
        data.pop("hooks", None)

    if data:
        _save(settings, data)
    else:
        settings.unlink()


def archive_traces(session_ids: list[str], out_dir: Path) -> list[Path]:
    """After the eval finishes, copy the trace jsonl for each session into
    out_dir/traces/ so the run is fully self-contained (turns can be
    re-judged offline without depending on ~/.cache state)."""
    from tracer import trace_dir

    dest = out_dir / "traces"
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for sid in session_ids:
        if not sid:
            continue
        src = trace_dir() / f"{sid}.jsonl"
        if not src.exists():
            continue
        target = dest / f"{sid}.jsonl"
        shutil.copy2(src, target)
        copied.append(target)
    return copied


# ── standalone-runner mode ───────────────────────────────────────────────
# Optional: use eval_runner.py directly to wrap a shell command, mirroring
# the handoff's original CLI form. Not used by run_eval.py — that path calls
# inject() / archive_traces() directly for better control.

def _cli() -> int:
    import subprocess

    if len(sys.argv) < 3:
        sys.exit(
            "usage: eval_runner.py <working_dir> <command> [args...]\n"
            "  Injects PostToolUse hook into working_dir/.claude/settings.json,\n"
            "  runs command, restores settings on exit."
        )
    working_dir = Path(sys.argv[1]).resolve()
    cmd = sys.argv[2:]

    inject(working_dir)
    try:
        return subprocess.run(cmd, cwd=working_dir).returncode
    finally:
        restore(working_dir)


if __name__ == "__main__":
    sys.exit(_cli())
