"""ToolRegistry loader.

YAML declaration example:
    priority: alpha            # alpha | beta | manifest_order
    tools:
      - name: get_order
        alpha:
          module: "capabilities.tool_calling.examples.local_tools"
          function: "get_order"
          timeout_ms: 800
        beta:
          endpoint: "https://internal.example.com/api/orders"
          method: "POST"
          timeout_ms: 5000
        description: "Query order"

Loading strategy:
- Alpha-track functions loaded dynamically via ``importlib``; when a module is missing, the tool retains only the beta track.
- Beta track is declaration-only; invocation is done by dispatcher injecting ``beta_invoker``.
"""
from __future__ import annotations

import importlib
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Import arbitrator via relative path (Phase 2 shared infrastructure)
import sys
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from scripts.lib.arbitrator import (  # noqa: E402
    AlphaTool,
    BetaTool,
    ToolCallResult,
    ToolRegistry,
)

logger = logging.getLogger(__name__)

_DEFAULT_REGISTRY_FILE = Path(
    os.getenv(
        "TC_REGISTRY_FILE",
        str(Path(__file__).resolve().parent.parent / "data" / "tools.yaml"),
    )
)


class ToolRegistryLoader:
    def __init__(self, registry_file: Optional[Path] = None) -> None:
        self._lock = threading.RLock()
        self._registry_file = Path(registry_file) if registry_file else _DEFAULT_REGISTRY_FILE
        self._registry: ToolRegistry = ToolRegistry()
        self._descriptions: Dict[str, str] = {}
        if self._registry_file.exists():
            self.reload()

    @property
    def registry(self) -> ToolRegistry:
        with self._lock:
            return self._registry

    def reload(self) -> int:
        if not self._registry_file.exists():
            return 0
        raw = yaml.safe_load(self._registry_file.read_text(encoding="utf-8")) or {}
        priority = (raw.get("priority") or "alpha").strip()
        new_reg = ToolRegistry(default_priority=priority)
        descriptions: Dict[str, str] = {}
        for tool_def in raw.get("tools") or []:
            name = str(tool_def.get("name") or "").strip()
            if not name:
                continue
            descriptions[name] = str(tool_def.get("description", ""))
            alpha_def = tool_def.get("alpha")
            beta_def = tool_def.get("beta")
            if alpha_def:
                func = self._load_callable(alpha_def)
                if func is not None:
                    new_reg.register_alpha(
                        AlphaTool(
                            name=name,
                            func=func,
                            timeout_ms=int(alpha_def.get("timeout_ms", 1000)),
                            description=descriptions[name],
                        )
                    )
            if beta_def and beta_def.get("endpoint"):
                new_reg.register_beta(
                    BetaTool(
                        name=name,
                        endpoint=str(beta_def["endpoint"]),
                        method=str(beta_def.get("method", "POST")),
                        timeout_ms=int(beta_def.get("timeout_ms", 5000)),
                        headers=dict(beta_def.get("headers") or {}),
                        description=descriptions[name],
                    )
                )
        with self._lock:
            self._registry = new_reg
            self._descriptions = descriptions
        return len(descriptions)

    def list_tools(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._registry.list_tools()

    def call(
        self,
        name: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        priority: Optional[str] = None,
    ) -> ToolCallResult:
        return self._registry.call(
            name,
            params,
            priority=priority,
            beta_invoker=_default_beta_invoker,
        )

    @staticmethod
    def _load_callable(alpha_def: Dict[str, Any]):
        mod_name = alpha_def.get("module")
        func_name = alpha_def.get("function")
        if not mod_name or not func_name:
            return None
        module = None
        try:
            module = importlib.import_module(mod_name)
        except ImportError:
            # Fallback: capability directory name has hyphens (tool-calling), standard import cannot resolve it
            # capabilities.tool_calling.* - switched to file-path-based loading (registry knows its own location).
            module = ToolRegistryLoader._load_module_by_path(mod_name)
        if module is None:
            logger.warning("alpha tool module not loadable: %s", mod_name)
            return None
        return getattr(module, func_name, None)

    @staticmethod
    def _load_module_by_path(mod_name: str):
        """Map dotted module name to file path within capability package and load.

        Convention: module name like ``capabilities.tool_calling.examples.local_tools``,
        take the ``examples`` segment and everything after as the path relative to ``<capability_root>``.
        """
        import importlib.util

        cap_root = Path(__file__).resolve().parent.parent  # capabilities/tool-calling/
        parts = mod_name.split(".")
        # Strip capabilities.<cap> prefix (regardless of underscores / hyphens), keep the examples/... tail
        tail: List[str] = []
        seen_examples = False
        for p in parts:
            if p == "examples":
                seen_examples = True
            if seen_examples:
                tail.append(p)
        if not tail:
            tail = parts[-2:]  # Fallback: take last two segments
        file_path = cap_root.joinpath(*tail).with_suffix(".py")
        if not file_path.is_file():
            return None
        qual = "_tc_local_" + "_".join(tail)
        cached = sys.modules.get(qual)
        if cached is not None:
            return cached
        spec = importlib.util.spec_from_file_location(qual, file_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[qual] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001
            sys.modules.pop(qual, None)
            logger.warning("alpha tool file load failed %s: %s", file_path, exc)
            return None
        return module


# ---------------------------------------------------------------------------
# Beta-track default implementation: requests sync POST / GET
# ---------------------------------------------------------------------------
def _default_beta_invoker(tool: BetaTool, params: Dict[str, Any]) -> Any:
    import requests  # Already in skeleton requirements

    if not tool.endpoint.startswith("https://") and not tool.endpoint.startswith("http://localhost"):
        # Security: except localhost debugging, beta-track enforces HTTPS (manifest.security.network.enforce_https)
        raise RuntimeError(f"β endpoint must use HTTPS: {tool.endpoint}")
    headers = {"Content-Type": "application/json", **tool.headers}
    timeout = max(tool.timeout_ms, 100) / 1000.0
    method = tool.method.upper()
    if method == "GET":
        resp = requests.get(tool.endpoint, params=params, headers=headers, timeout=timeout)
    else:
        resp = requests.request(
            method, tool.endpoint, json=params, headers=headers, timeout=timeout
        )
    resp.raise_for_status()
    ctype = resp.headers.get("Content-Type", "")
    if "application/json" in ctype:
        return resp.json()
    return resp.text


# ---------------------------------------------------------------------------
# Global singleton (used by dispatcher / router)
# ---------------------------------------------------------------------------
_global_loader = ToolRegistryLoader()


def get_loader() -> ToolRegistryLoader:
    return _global_loader
