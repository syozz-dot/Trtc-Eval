"""Phase 3 — internal-contract eval (white-box trace assertions).

Files in this package are eval-only. They are NEVER distributed to end users
via npm — Trtc-Eval owns them entirely, and agent-skills has no dependency
on any of them.

Layers:

  tracer.py               — thin emit_trace() shim, writes ~/.cache/trtc-traces/
  trace_posttooluse.py    — Claude Code PostToolUse hook script
  eval_runner.py          — inject/restore settings.json + archive traces

Usage: called from run_eval.py when --with-trace is set. Do not run these
files directly on user machines.
"""
