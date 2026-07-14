**IDE**: `claude-code`  ·  **日期**: 2026-07-14  ·  **out-dir**: `corpus-smoke-2026-07-14`  ·  **范围**: 2/8 条 corpus seed

## 📋 TL;DR

- ✅ **触发正确性**: 2/2 通过（skill 都按预期触发）

### ⚠️ 发现 1 个能力暗雷
_触发都对了，但 AI 的回答有覆盖缺口_：

- 🟡 **Live** · _TUIRoomEngine 点赞事件回调_  
  → **只靠 docsbot** — 本地文档无覆盖，docsbot 挂就失守

### 🟢 1 个覆盖完整

- **Chat** · _Vue3 UIKit 消息列表头像配置_ （读了 4 份本地文档）

### ⏱ 耗时/消耗对比

_tool 数量 ≈ token 消耗；error 多说明可能有 fallback 循环_

- **Chat**: 33 tools · 8 errors · 🐢 慢（多次 fallback）
- **Live**: 9 tools · 1 errors · 🚀 快

---

<details>
<summary><b>📊 技术细节</b>（点开看：8 维度触发观察点 · bucket 判定 · 每条数据源）</summary>

### 触发正确性 — 每条 case

| Case | Product | Intent | Pass | Fail / Concern |
|---|---|---|:---:|---|
| P2-CORPUS-CHAT-001 | Chat | capability_lookup | ✅ | - |
| P2-CORPUS-LIVE-001 | Live | api_lookup | ✅ | - |

### 能力覆盖 — 每条数据源

| Case | Product | 结论 | 数据源 | Tools | Errors |
|---|---|---|---|---:|---:|
| P2-CORPUS-CHAT-001 | Chat | 🟢 覆盖完整 | 4 份本地文档 + webfetch 兜底 | 33 | 8 |
| P2-CORPUS-LIVE-001 | Live | 🟡 只靠 docsbot | docsbot | 9 | 1 |

### 按产品聚合

| Product | Cases | 🟢 | 🟡 | 🟠 | 🔵 | 🚨 | 结论 |
|---|---:|---:|---:|---:|---:|---:|---|
| Chat | 1 | 1 | 0 | 0 | 0 | 0 | 🟢 本地覆盖完整 |
| Live | 1 | 0 | 1 | 0 | 0 | 0 | 🟡 全部依赖 docsbot |

</details>

<details>
<summary><b>📖 术语说明</b>（点开看：这条报告 vs Skill Eval Score Report 的区别 · bucket 定义 · 观察点分级）</summary>

**PR 上会出现两条评论，各答一个问题**：

| 评论 | 回答的问题 |
|---|---|
| **Skill Eval Score Report** | skill/工具**有没有按预期触发**？（涵盖所有 P2 case，不只 corpus）|
| **Corpus Coverage Report**（本条）| AI 的**回答质量**如何？能力有没有覆盖用户提问？|

**Bucket（能力覆盖分类）**：

| Bucket | 含义 | 说明 |
|---|---|---|
| 🟢 `A` 覆盖完整 | | 本地文档命中，或 docsbot + 本地双命中 |
| 🟡 `B` 只靠 docsbot | | 本地文档无覆盖，docsbot 挂就失守 |
| 🟠 `C` 拒答 | | skill 明说不支持 / 找不到 |
| 🔵 `D` 追问无路 | | 反复追问最终没答上 |
| 🚨 `E?` 疑似瞎编 | | 有回答但没检索源，可能是幻觉 |

**触发正确性观察点分级**（如果你看到 route_level1 fail 但整体 pass，就是这个原因）：
- `route_triggered` = **critical** → 主 skill 未触发时整 case fail
- `route_level1` / `route_level2` = **soft** → 路由准确度还没优化，N 只记 minor concern
- 其他 hard 观察点 → 任一 N 都会拖 case fail

</details>

---

**已知限制**：
- 本次覆盖 2/8 条 corpus seed
- 🚨 疑似瞎编 需 LLM judge 二次确认，本工具不做
