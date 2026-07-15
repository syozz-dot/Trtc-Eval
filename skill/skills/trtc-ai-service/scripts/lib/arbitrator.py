"""α/β dual-track tool-call arbitration.

| Track | Implementation | Triggered When                           |
|:-----:|:---------------|:-----------------------------------------|
| α     | Local function | Default priority (low latency, zero network overhead) |
| β     | Remote API     | α unavailable (not registered / failed / timed out)   |

Arbitration rules (manifest.tool_calling node):
    priority: alpha | beta | manifest_order
    timeout_ms_alpha / timeout_ms_beta
    retry_alpha / retry_beta

Risk P1 mitigation: when both tracks exist, decide by the priority field; auto-fallback when α is unavailable.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class AlphaTool:
    name: str
    func: Callable[..., Any]
    timeout_ms: int = 1000
    description: str = ""


@dataclass
class BetaTool:
    name: str
    endpoint: str
    method: str = "POST"
    timeout_ms: int = 5000
    headers: Dict[str, str] = field(default_factory=dict)
    description: str = ""


@dataclass
class ToolCallResult:
    tool: str
    track: str           # alpha | beta
    ok: bool
    output: Any = None
    error: str = ""
    latency_ms: int = 0
    fallback_chain: List[str] = field(default_factory=list)


class ToolRegistry:
    """同名工具可同时注册 α 与 β，由 ``call`` 仲裁。"""

    def __init__(self, *, default_priority: str = "alpha") -> None:
        if default_priority not in ("alpha", "beta", "manifest_order"):
            raise ValueError(f"invalid priority: {default_priority}")
        self._alpha: Dict[str, AlphaTool] = {}
        self._beta: Dict[str, BetaTool] = {}
        self._priority = default_priority

    # 注册 -----------------------------------------------------------------
    def register_alpha(self, tool: AlphaTool) -> None:
        self._alpha[tool.name] = tool

    def register_beta(self, tool: BetaTool) -> None:
        self._beta[tool.name] = tool

    def list_tools(self) -> List[Dict[str, Any]]:
        names = sorted(set(self._alpha) | set(self._beta))
        return [
            {
                "name": n,
                "alpha": self._alpha[n].description if n in self._alpha else None,
                "beta": self._beta[n].description if n in self._beta else None,
                "priority": self._priority,
            }
            for n in names
        ]

    # 调用 -----------------------------------------------------------------
    def call(
        self,
        name: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        priority: Optional[str] = None,
        beta_invoker: Optional[Callable[[BetaTool, Dict[str, Any]], Any]] = None,
    ) -> ToolCallResult:
        """执行工具调用，按 priority 决策并自动降级。

        beta_invoker 由调用方注入（避免本模块依赖 requests），
        默认只在 α 可用时跑 α，β 路径必须由调用方实现网络调用。
        """
        params = params or {}
        priority = priority or self._priority
        chain: List[str] = []
        order = self._resolve_order(name, priority)
        last_error = ""
        for track in order:
            chain.append(track)
            if track == "alpha":
                tool = self._alpha.get(name)
                if not tool:
                    last_error = f"alpha not registered: {name}"
                    continue
                start = time.perf_counter()
                try:
                    out = tool.func(**params)
                    return ToolCallResult(
                        tool=name, track="alpha", ok=True, output=out,
                        latency_ms=int((time.perf_counter() - start) * 1000),
                        fallback_chain=chain,
                    )
                except Exception as exc:  # noqa: BLE001
                    last_error = f"alpha:{type(exc).__name__}:{exc}"
            else:  # beta
                tool = self._beta.get(name)
                if not tool:
                    last_error = f"beta not registered: {name}"
                    continue
                if beta_invoker is None:
                    last_error = "beta_invoker not provided"
                    continue
                start = time.perf_counter()
                try:
                    out = beta_invoker(tool, params)
                    return ToolCallResult(
                        tool=name, track="beta", ok=True, output=out,
                        latency_ms=int((time.perf_counter() - start) * 1000),
                        fallback_chain=chain,
                    )
                except Exception as exc:  # noqa: BLE001
                    last_error = f"beta:{type(exc).__name__}:{exc}"
        return ToolCallResult(
            tool=name, track=chain[-1] if chain else "none",
            ok=False, error=last_error or "no track available",
            fallback_chain=chain,
        )

    # 仲裁 -----------------------------------------------------------------
    def _resolve_order(self, name: str, priority: str) -> List[str]:
        has_a = name in self._alpha
        has_b = name in self._beta
        if priority == "alpha":
            base = ["alpha", "beta"]
        elif priority == "beta":
            base = ["beta", "alpha"]
        else:  # manifest_order：以注册顺序为准（首次注册者优先）
            base = ["alpha", "beta"] if has_a and not has_b else (
                ["beta", "alpha"] if has_b and not has_a else ["alpha", "beta"]
            )
        return [t for t in base if (t == "alpha" and has_a) or (t == "beta" and has_b)]
