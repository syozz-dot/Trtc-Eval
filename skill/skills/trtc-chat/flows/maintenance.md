---
phase: maintenance
product: chat
platform: web
---

# Chat Maintenance Flow — Path C

> **调用方**：`trtc-chat/SKILL.md` Step 2 分流 Path C 时 Read 本文件。
>
> **职责**：维护 / 排障 / 减法 / 样式调整；**不**加载 slice。

## 执行

Read `../references/04-path-c-script.md`，从 C.1 执行完整 Path C 脚本。

可选：设 `active_flow=maintenance`（经 `tools.session write-batch`，禁止直接编辑 yaml）。

**禁止** `flow enter --phase maintenance`（`flow.py` 无此 phase；直读 reference 即可）。
