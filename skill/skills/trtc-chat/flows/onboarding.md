---
phase: onboarding
product: chat
platform: web
---

# Chat Onboarding Flow

> **调用方**：`trtc-chat/SKILL.md` Path A/B 集成时 Read 本文件。
>
> **职责**：Path A（0→1）与 Path B（增量）入口；`detect`→`slices` 全程 `active_flow=onboarding`；slice 循环由 `02-path-a-script` / `03-path-b-script` + `05-slice-loading.md` 驱动。
>
> **无 topic flow**：禁止 `enter --phase topic`。

## Session 副作用

```bash
cd "<当前 trtc skill 目录>"
python3 -m tools.flow enter --phase onboarding --product chat --platform web
```

> **flow_state 恢复协议**：`enter` 首次会清空 `flow_state`；enter 后**仅当** `flow_state.chat.phase` 为空/null 才补写：

```bash
PHASE=$(python3 -m tools.session read --field flow_state.chat.phase)
if [ -z "$PHASE" ] || [ "$PHASE" = "null" ]; then
  python3 -m tools.session read --field state_version --with-version
  python3 -m tools.session write-batch \
    --updates '{"flow_state": {"chat": {"phase": "detect", "chat_path": "A"}}}' \
    --expected-version <N>
fi
```

## Session 写协议

本文件内所有 session 写入都必须走 `tools.session` CLI，**不得直接编辑** `.trtc-session.yaml`。

```bash
python3 -m tools.session read --field state_version --with-version
python3 -m tools.session write-batch --updates '{...}' --expected-version <N>
```

- exit code **3**（CAS 冲突）→ 重读 version，重试一次
- 第二次仍 3 → 停止，告知 session 并发冲突

## 入口检查 — Path B 跨 turn（禁止 `reopen-add-feature`）

若 `status = completed` 且用户要加功能：

```bash
python3 -m tools.session write-batch --updates '{
  "status": "active",
  "intent": "integrate-feature",
  "active_flow": "onboarding",
  "flow_state": {"chat": {"phase": "slices", "chat_path": "B"}}
}' --expected-version <N>
```

**不变量**：`base_slices_applied` / `extension_slices_applied` / `integration_mode` 不得清空。

## 分流 pointer

| 条件 | Read |
|------|------|
| Path A（0→1） | `../references/02-path-a-script.md` + `../references/08-state-config.md` |
| Path B（增量） | `../references/03-path-b-script.md` |
| Slice 加载 | `../references/05-slice-loading.md` + `../references/execution-units.yaml` |
| Slice 文件 | `python3 -m tools.kb resolve slices/chat/web/<slice>.md` |
| Index | `python3 -m tools.kb resolve chat/web/index.yaml` |

首版**不用** `init_slice_queue.py` / `tools.apply` / `finalize_session.py`。

## Session 收尾（A.4 / B.5）

```bash
python3 -m tools.session write-batch \
  --updates '{"status": "completed", "flow_state": {"chat": {"phase": "done", "chat_path": "<A|B>"}}}' \
  --expected-version <N>
```
