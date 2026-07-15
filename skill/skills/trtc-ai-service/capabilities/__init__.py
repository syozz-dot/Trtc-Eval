"""capabilities namespace root.

Subdirectories use hyphenated names (manifest style), but Python modules require underscore names.
This file creates aliases on import as needed (only when the corresponding directory exists).

Example:
    capabilities.knowledge-base/  →  import capabilities.knowledge_base
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

# Hyphenated directory → underscore module alias
_ALIASES = {
    "knowledge-base": "knowledge_base",
    "tool-calling": "tool_calling",
    "human-handoff": "human_handoff",
    "session-summary": "session_summary",
    "digital-human": "digital_human",
}


def _install_alias(dirname: str, modname: str) -> None:
    full_dir = _ROOT / dirname
    if not full_dir.exists():
        return
    full_name = f"{__name__}.{modname}"
    if full_name in sys.modules:
        return
    # Register a namespace package that sub-modules can continue importing
    import types

    pkg = types.ModuleType(full_name)
    pkg.__path__ = [str(full_dir)]  # type: ignore[attr-defined]
    sys.modules[full_name] = pkg


for _d, _m in _ALIASES.items():
    _install_alias(_d, _m)
