"""
tools/state_machine.py
======================

TRTC AI Integration —— execution-step 状态机。

把 ``confirmed_plan`` 物化为 ``execution_queue``，并在 topic 阶段推进每个 step 的状态。

读写 session 全部经过 session.py（Session.load / Session.transaction），不直接操作 yaml。


============================================================
设计要点
============================================================

# 状态转移图

  not_started ──mark_slice_read──▶ slice_read ──mark_code_written──▶ code_written
                                                                          │
                                                                     apply.py
                                                                  ┌────┴────┐
                                                                  ▼         ▼
                                                           apply_passed  apply_failed
                                                                  │         │
                                                            用户"继续"    Edit 修改
                                                                  │         │
                                                                  ▼         ▼
                                                           user_confirmed code_written（回环）
                                                                  │
                                                                  ▼
                                                           下一个 step / all_done


# execution_queue 的 step 结构

  {
    id:     str   全局唯一，单 slice 时 = slice_id，多 slice 合并时 = 拼接
    type:   str   "slice" | "unit"
    title:  str   显示用
    status: str   "pending" | "done"
                  （in_progress 由 current_execution_state 表达，不在 step.status 重复）
    slices: list  该 step 包含的 slice id 列表（1 个或多个）
  }


# execution_granularity 和 delivery_units 的位置

  session.flow_state.execution_granularity  （conference 专有，默认 slice 模式）
  session.flow_state.delivery_units         （session 级覆盖，null = 从 execution-units.yaml 读）


# execution-units.yaml 路径

  {repo_root}/skills/{active_domain_skill}/references/execution-units.yaml
  active_domain_skill 从 session.active_domain_skill 读取（如 "trtc-conference"）。


============================================================
公开接口
============================================================

# Python API

  from tools.state_machine import StateMachine

  sm = StateMachine.load()                     # 读 session，校验状态机已初始化
  scope = sm.current_scope()                   # 返回当前 step 详情
  next_state = sm.advance("mark_slice_read")   # 推进状态
  summary = sm.status()                        # 完整队列 + 当前状态


# CLI

  python3 -m tools.state_machine init
  python3 -m tools.state_machine advance <transition>
  python3 -m tools.state_machine status

  退出码：
    0 = 成功
    1 = 输入错误（transition 非法 / 参数缺失）
    2 = 资源缺失（session 不存在 / queue 未初始化 / confirmed_plan 缺失）
    3 = 状态错误（非法状态转移 / all_done 时继续推进）
    4 = CAS 冲突（caller 重读重试）
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Optional

# ============================================================
# session.py 依赖
# ============================================================

try:
    from tools.session import (
        ConflictError as SessionConflictError,
        MissingError as SessionMissingError,
        Session,
        SessionError,
        emit_trace as _emit_trace,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tools.session import (  # type: ignore
        ConflictError as SessionConflictError,
        MissingError as SessionMissingError,
        Session,
        SessionError,
        emit_trace as _emit_trace,
    )


# ============================================================
# Constants
# ============================================================

_TRANSITIONS: dict[tuple[str, str], str] = {
    ("not_started",  "mark_slice_read"):     "slice_read",
    ("slice_read",   "mark_code_written"):   "code_written",
    ("code_written", "mark_apply_passed"):   "apply_passed",
    ("code_written", "mark_apply_failed"):   "apply_failed",
    ("apply_failed", "mark_code_written"):   "code_written",
    ("apply_passed", "mark_user_confirmed"): "ADVANCE_INDEX",
}

KNOWN_TRANSITIONS = {t for (_, t) in _TRANSITIONS}

THIS_FILE = Path(__file__).resolve()
# skills/trtc/tools/state_machine.py → repo_root
DEFAULT_REPO_ROOT = THIS_FILE.parent.parent.parent.parent
ENV_REPO_ROOT = "TRTC_REPO_ROOT"


# ============================================================
# Errors
# ============================================================

class StateMachineError(Exception):
    """状态机异常基类。"""


class NotInitializedError(StateMachineError):
    """execution_queue 尚未初始化（需先调 init）。"""


class InvalidTransitionError(StateMachineError):
    """非法状态转移。"""


class AllDoneError(StateMachineError):
    """execution_queue 已全部完成，不允许继续推进。"""


class SessionStateError(StateMachineError):
    """session 相关错误（不存在 / 损坏 / confirmed_plan 缺失等）。"""


# ============================================================
# Path helpers
# ============================================================

def _repo_root() -> Path:
    env = os.environ.get(ENV_REPO_ROOT)
    if env:
        return Path(env).resolve()
    return DEFAULT_REPO_ROOT


def _execution_units_path(domain_skill: str) -> Path:
    """根据 domain skill 名定位 execution-units.yaml。"""
    return _repo_root() / "skills" / domain_skill / "references" / "execution-units.yaml"


# ============================================================
# Step builder helpers
# ============================================================

def _step_id_from_slices(slice_ids: list[str]) -> str:
    if len(slice_ids) == 1:
        return slice_ids[0]
    return "__".join(s.split("/", 1)[-1] for s in slice_ids)


def _step_type(slice_ids: list[str]) -> str:
    return "unit" if len(slice_ids) > 1 else "slice"


def _make_step(step_id: str, title: str, slice_ids: list[str], status: str = "pending") -> dict:
    return {
        "id": step_id,
        "type": _step_type(slice_ids),
        "title": title,
        "status": status,
        "slices": slice_ids,
    }


def _flatten_slices(queue: list[dict]) -> list[str]:
    return [sid for step in queue for sid in step.get("slices", [])]


def _build_slice_steps(plan: list[str]) -> list[dict]:
    return [_make_step(sid, sid, [sid]) for sid in plan]


def _build_unit_steps(raw_units: list[dict], plan: list[str]) -> list[dict]:
    """按 delivery_unit 定义分组，只包含 confirmed_plan 里的 slice。

    同一 slice 出现在多个 unit 里时，第一个命中的 unit 优先（first-match wins）。
    单个 unit 内的重复 slice 视为配置错误，报错。
    """
    remaining = list(plan)
    steps: list[dict] = []

    for raw in raw_units:
        group = raw.get("slices") or []

        # 只检查单个 unit 内的重复（跨 unit 允许 first-match wins）
        intra_dupes = sorted({sid for sid in group if group.count(sid) > 1})
        if intra_dupes:
            raise StateMachineError(
                f"delivery unit '{raw.get('id')}' 内有重复 slice：{', '.join(intra_dupes)}"
            )

        slice_ids = [sid for sid in group if sid in remaining]
        if len(slice_ids) < 2:
            continue
        step_id = raw.get("id") or _step_id_from_slices(slice_ids)
        steps.append(_make_step(step_id, raw.get("title") or step_id, slice_ids))
        for sid in slice_ids:
            remaining.remove(sid)

    for sid in remaining:
        steps.append(_make_step(sid, sid, [sid]))

    order = {sid: i for i, sid in enumerate(plan)}
    steps.sort(key=lambda step: min(order[sid] for sid in step["slices"]))
    return steps


def _load_scenario_units(domain_skill: str, scenario_id: str) -> list[dict]:
    """从 execution-units.yaml 读取指定 scenario 的 delivery_units。"""
    path = _execution_units_path(domain_skill)
    if not path.exists():
        return []
    import yaml
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise StateMachineError(f"execution-units.yaml 解析失败：{e}")
    return (
        (config.get("scenarios") or {})
        .get(scenario_id, {})
        .get("delivery_units") or []
    )


def _load_compat(path: str | Path) -> "StateMachine":
    """兼容旧调用方：显式 session 路径加载状态机。"""
    return StateMachine.load(path=str(path))


def _legacy_flow_fields(sess: Session) -> tuple[Optional[str], Optional[list[dict]]]:
    """兼容 v1/v1.5 fixture：顶层 execution_granularity / delivery_units。"""
    flow_state: dict = sess.flow_state or {}
    granularity = flow_state.get("execution_granularity")
    delivery_units = flow_state.get("delivery_units")

    if granularity is None:
        granularity = sess.get("execution_granularity")
    if delivery_units is None:
        delivery_units = sess.get("delivery_units")

    return granularity, delivery_units


def _legacy_domain_skill(sess: Session) -> str:
    return sess.active_domain_skill or f"trtc-{sess.product}" if sess.product else ""


def _legacy_scenario_id(sess: Session) -> str:
    return sess.active_scenario or sess.get("scenario") or ""


# ============================================================
# StateMachine class
# ============================================================

class StateMachine:
    """execution_queue 状态机。

    无持久状态——session.yaml 是唯一 SoT。
    每次操作：load session → 操作 → transaction 写回。
    """

    def __init__(self, sess: Session):
        self._sess = sess

    @classmethod
    def load(
        cls,
        path: Optional[str] = None,
        project_root: Optional[str] = None,
    ) -> "StateMachine":
        """加载 session，返回状态机实例。调用 init() 后方可调用 advance()。

        Raises:
          SessionStateError: session 不存在 / 损坏
        """
        try:
            sess = Session.load(path=path, project_root=project_root)
        except SessionMissingError:
            raise SessionStateError("session 不存在，请先完成 onboarding 并初始化 session")
        except SessionError as e:
            raise SessionStateError(f"session 加载失败：{e}")
        return cls(sess)

    # ---- init ----

    def init(self) -> None:
        """把 confirmed_plan 物化为 execution_queue。

        幂等：queue 已存在且与 confirmed_plan 一致时直接返回。
        confirmed_plan 缺失时抛 SessionStateError。

        读取顺序：
          execution_granularity → session.flow_state.execution_granularity
          delivery_units        → session.flow_state.delivery_units
                                   或 execution-units.yaml（按 active_scenario 查）
        """
        sess = self._sess
        plan: list[str] = sess.confirmed_plan or []
        if not plan:
            raise SessionStateError(
                "confirmed_plan 为空——onboarding 应在调用 init 前写入 confirmed_plan"
            )

        existing_queue: list[dict] = sess.execution_queue or []
        if existing_queue:
            if _flatten_slices(existing_queue) == plan:
                _emit_trace({
                    "session_id": sess.session_id,
                    "event": "state_machine.init.idempotent",
                })
                return
            raise StateMachineError(
                "execution_queue 已存在且与 confirmed_plan 不一致——"
                "如需重置，请手动清除 execution_queue / current_execution_index / "
                "current_execution_state 后重试"
            )

        # 读 conference 专有字段（在 flow_state 里）
        granularity, delivery_units = _legacy_flow_fields(sess)

        if granularity in {"unit", "delivery_unit"}:
            if not delivery_units:
                domain_skill = _legacy_domain_skill(sess)
                scenario_id = _legacy_scenario_id(sess)
                delivery_units = _load_scenario_units(domain_skill, scenario_id)
            if not delivery_units:
                # unit 模式但找不到分组配置，降级为 slice 模式并记录 trace
                _emit_trace({
                    "session_id": sess.session_id,
                    "event": "state_machine.init.unit_degraded_to_slice",
                    "reason": "delivery_units 为空，execution-units.yaml 未找到对应 scenario",
                    "domain_skill": _legacy_domain_skill(sess),
                    "active_scenario": _legacy_scenario_id(sess),
                })
                queue = _build_slice_steps(plan)
            else:
                queue = _build_unit_steps(delivery_units, plan)
        else:
            queue = _build_slice_steps(plan)

        try:
            with sess.transaction() as upd:
                upd.execution_queue = queue
                upd.current_execution_index = 0
                upd.current_execution_state = "not_started"
        except SessionConflictError:
            raise
        except SessionError as e:
            raise SessionStateError(f"写入 session 失败：{e}")

        _emit_trace({
            "session_id": sess.session_id,
            "event": "state_machine.init",
            "granularity": granularity or "slice",
            "steps": len(queue),
            "plan_slices": len(plan),
        })

    # ---- current_scope ----

    def current_scope(self) -> dict:
        """返回当前 step 详情（供 Python API 调用方使用）。"""
        sess = self._sess
        queue: list[dict] = sess.execution_queue or []
        if not queue:
            return {"initialised": False, "reason": "execution_queue 未初始化"}

        idx: int = sess.current_execution_index or 0
        state: str = sess.current_execution_state or "not_started"

        if state == "all_done":
            return {
                "initialised": True,
                "index": idx,
                "state": "all_done",
                "total": len(queue),
                "id": None,
                "title": None,
                "type": None,
                "kind": "execution",
                "slice_ids": [],
            }

        if idx < 0 or idx >= len(queue):
            return {"initialised": False, "reason": "execution cursor 越界"}

        step = queue[idx]
        slice_ids: list[str] = step.get("slices") or [step.get("id")]
        return {
            "initialised": True,
            "index": idx,
            "state": state,
            "total": len(queue),
            "id": step.get("id"),
            "title": step.get("title") or step.get("id"),
            "type": step.get("type") or _step_type(slice_ids),
            "kind": step.get("type") or _step_type(slice_ids),
            "slice_ids": slice_ids,
        }

    # ---- advance ----

    def advance(self, transition: str) -> str:
        """推进状态机，返回新状态。

        Raises:
          InvalidTransitionError: 非法 transition 名
          AllDoneError: 已经 all_done
          NotInitializedError: queue 未初始化
        """
        if transition not in KNOWN_TRANSITIONS:
            raise InvalidTransitionError(
                f"未知 transition：'{transition}'。"
                f"可用：{sorted(KNOWN_TRANSITIONS)}"
            )

        sess = self._sess
        queue: list[dict] = sess.execution_queue or []
        if not queue:
            raise NotInitializedError("execution_queue 未初始化，请先调用 init")

        idx: int = sess.current_execution_index or 0
        state: str = sess.current_execution_state or "not_started"

        if state == "all_done":
            raise AllDoneError("execution_queue 已全部完成，不允许继续推进")

        next_state = _TRANSITIONS.get((state, transition))
        if next_state is None:
            allowed = sorted(t for (s, t) in _TRANSITIONS if s == state)
            raise InvalidTransitionError(
                f"当前状态 '{state}' 不允许 transition '{transition}'。"
                f"当前允许：{allowed}"
            )

        if next_state == "ADVANCE_INDEX":
            new_idx = idx + 1
            final_state = "all_done" if new_idx >= len(queue) else "not_started"

            # 深拷贝后再修改，避免 transaction 失败时污染 in-memory session
            queue_copy = copy.deepcopy(queue)
            step_copy = queue_copy[idx]
            step_copy["status"] = "done"
            evidence_ids = [step_copy.get("id")] + list(step_copy.get("slices", []))

            try:
                with sess.transaction() as upd:
                    upd.execution_queue = queue_copy
                    upd.current_execution_index = new_idx
                    upd.current_execution_state = final_state
            except SessionConflictError:
                raise  # 让 CAS 冲突保持原始类型，caller 可重读重试
            except SessionError as e:
                raise SessionStateError(f"写入 session 失败：{e}")

            # transaction 成功后再删除证据文件，保证原子性
            sess_path = Path(sess.path)
            for eid in [e for e in evidence_ids if e]:
                ev = sess_path.parent / ".trtc-apply-evidence" / (eid.replace("/", "__") + ".json")
                try:
                    ev.unlink()
                except FileNotFoundError:
                    pass

            _emit_trace({
                "session_id": sess.session_id,
                "event": "state_machine.advance",
                "transition": transition,
                "from_state": state,
                "to_state": final_state,
                "step_index": idx,
            })
            return final_state

        try:
            with sess.transaction() as upd:
                upd.current_execution_state = next_state
        except SessionConflictError:
            raise  # 让 CAS 冲突保持原始类型
        except SessionError as e:
            raise SessionStateError(f"写入 session 失败：{e}")

        _emit_trace({
            "session_id": sess.session_id,
            "event": "state_machine.advance",
            "transition": transition,
            "from_state": state,
            "to_state": next_state,
            "step_index": idx,
        })
        return next_state

    # ---- status ----

    def status(self) -> dict:
        """返回完整队列状态（CLI / 调试用）。"""
        sess = self._sess
        queue: list[dict] = sess.execution_queue or []
        if not queue:
            return {"initialised": False, "reason": "execution_queue 未初始化"}

        idx: int = sess.current_execution_index or 0
        state: str = sess.current_execution_state or "not_started"
        step = queue[idx] if idx < len(queue) else None
        slice_ids: list[str] = (step.get("slices") if step else None) or []

        done = sum(1 for s in queue if s.get("status") == "done")

        return {
            "initialised": True,
            "index": idx,
            "state": state,
            "total": len(queue),
            "done": done,
            "remaining": len(queue) - done,
            "kind": step.get("type") if step else "execution",
            "current_id": step.get("id") if step else None,
            "current_title": step.get("title") if step else None,
            "current_type": step.get("type") if step else None,
            "current_slice_id": slice_ids[0] if slice_ids else None,
            "current_unit_id": (step.get("id") if step and step.get("type") == "unit" else None),
            "slice_ids": slice_ids,
            "queue": queue,
        }


# ============================================================
# Backward-compatible module helpers
# ============================================================

def init_queue(session_path: str | Path) -> None:
    """旧接口兼容层：按显式 session 路径初始化 execution_queue。"""
    try:
        _load_compat(session_path).init()
    except StateMachineError as exc:
        raise RuntimeError(str(exc)) from exc


def current_scope(session_path: str | Path) -> dict:
    """旧接口兼容层：返回当前 step。"""
    try:
        return _load_compat(session_path).current_scope()
    except SessionStateError:
        return {"initialised": False, "reason": "session file missing"}


def current_slice(session_path: str | Path) -> tuple[Optional[int], Optional[str], Optional[str]]:
    """旧接口兼容层：返回当前 step 的首个 slice。"""
    scope = current_scope(session_path)
    if not scope.get("initialised"):
        return (None, None, None)
    if scope.get("state") == "all_done":
        return (scope.get("index"), None, "all_done")
    slice_ids = scope.get("slice_ids") or []
    return (scope.get("index"), slice_ids[0] if slice_ids else None, scope.get("state"))


def advance(session_path: str | Path, transition: str) -> str:
    """旧接口兼容层：按显式 session 路径推进状态机。"""
    try:
        return _load_compat(session_path).advance(transition)
    except StateMachineError as exc:
        raise RuntimeError(str(exc)) from exc


def status(session_path: str | Path) -> dict:
    """旧接口兼容层：返回完整队列状态。"""
    try:
        return _load_compat(session_path).status()
    except SessionStateError:
        return {"initialised": False, "reason": "session file missing"}


# ============================================================
# CLI
# ============================================================

def _cli_init(_args: list[str]) -> int:
    try:
        sm = StateMachine.load()
        sm.init()
    except SessionStateError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except StateMachineError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    except SessionConflictError as e:
        print(f"ERROR (CAS): {e}", file=sys.stderr)
        return 4
    print("init: execution_queue 物化完成")
    return 0


def _cli_advance(args: list[str]) -> int:
    if not args:
        print("ERROR: 必须提供 transition 名", file=sys.stderr)
        print(f"可用：{sorted(KNOWN_TRANSITIONS)}", file=sys.stderr)
        return 1
    transition = args[0]
    try:
        sm = StateMachine.load()
        new_state = sm.advance(transition)
    except InvalidTransitionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except (NotInitializedError, SessionStateError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except AllDoneError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    except SessionConflictError as e:
        print(f"ERROR (CAS): {e}", file=sys.stderr)
        return 4
    print(f"advance: {transition} → {new_state}")
    return 0


def _cli_status(_args: list[str]) -> int:
    try:
        sm = StateMachine.load()
        result = sm.status()
    except SessionStateError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    handlers = {
        "init":    _cli_init,
        "advance": _cli_advance,
        "status":  _cli_status,
    }
    handler = handlers.get(cmd)
    if not handler:
        print(f"未知子命令：{cmd}", file=sys.stderr)
        print(f"可用：{', '.join(handlers)}", file=sys.stderr)
        return 1
    return handler(rest)


if __name__ == "__main__":
    raise SystemExit(main())
