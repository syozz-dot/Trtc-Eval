# 05 - Slice 命中机制 + 多候选选择 + 兜底

> dispatcher 在以下三个时机主动 `read_file` 本文件：
> - 路径 A 的 **A.1.5 被动解析**（命中扩展 slice / 收集 unsupported_intents）
> - 路径 A 的 A.5 引导菜单选中后
> - 路径 B 的 B.2 听需求阶段

## 5.1 命中流程

```
1. Bash `python3 -m tools.kb resolve chat/web/index.yaml` → Read
   （含所有 slice 的 frontmatter 摘要：id / description / trigger-keywords /
    applies-to / sdk-version / prerequisites）

2. 解析用户需求（动词 + 名词 + 业务术语）
   - 动词：发送 / 加 / 实现 / 接 / 显示 / 接收 / 撤回 / 搜索 / ...
   - 名词：消息 / 卡片 / 群 / 会话 / 已读 / ...
   - 业务术语：订单 / 商品 / 优惠券 / 红包 / 投票 / 客服 / 评价 / ...

3. 在 trigger-keywords 中找语义匹配的 slice
   ⚠ 注意：trigger-keywords 是给 LLM 看的元数据，不是 grep 字段。
     用语义能力做模糊命中，不依赖精确字符串匹配。

4. 多个候选时，按下面 §5.2 排序

5. 命中 → read_file 读 slice 完整内容 → 进入写代码阶段

6. 完全没命中 → §5.3 兜底
   - 路径 A.1.5 场景：归入 unsupported_intents，A.4 口头收尾时一并提示，**不**进 §5.3 兜底实现
   - 路径 B B.2 场景：进 §5.3 兜底实现 + 提 issue
```

## 5.2 多候选排序

按以下优先级降序：

1. `applies-to` 匹配当前项目集成方式（`tuikit-atomicx-vue3`）
2. `sdk-version` 匹配项目实际 SDK 版本（`package.json` 里的 `tuikit-atomicx-vue3` 版本）
3. `prerequisites` 链与 `session（session_context.chat）` 已完成项匹配的越多越优
   - 路径 A.1.5 场景：`base_slices_applied` 视为已完成（4 件套基础 + 已入列的 extensionSlices）
   - 路径 B 场景：`base_slices_applied` + `extension_slices_applied` 都视为已完成
4. `trigger-keywords` 命中关键词数量

最后仍并列时：

```
> 我找到几个 slice 都对得上：
>   1. send-custom-message（自定义订单卡片）
>   2. send-image-advanced（图片消息）
>
> 你描述的 "我要发订单消息" 是哪种？
> 还是先做订单卡片，图片放它的字段里？
```

让用户做最后决策，不要替用户选。

## 5.3 兜底分支（无 slice 命中）

### 路径 A.1.5 场景（被动解析阶段）

❌ **不**走 §5.3 自由实现。命中失败的意图归入 `unsupported_intents`：

```jsonc
{
  "raw": "把消息翻译成英文",        // 用户原话
  "intent": "message-translation",  // dispatcher 抽取的意图标签
  "askedAt": "2026-05-20T15:22:00Z"
}
```

A.4 收尾时在 agent 回复里说一次（按意图类别给 fallback 建议，详见 `./02-path-a-script.md` § A.4），**不写额外文件**。

### 路径 B B.2 场景（已集成项目的二次增量）

❗ **未命中 slice 时，禁止自由实现**——不准基于训练数据猜测 SDK 用法、不准用 `chat.xxx` 旧 API 硬写代码。

输出以下话术后**停止**，等待用户反馈：

```
> 抱歉，我的知识库里暂时没有找到对应这个功能的实现指南，目前无法为您实现该功能。
>
> 您可以通过工单向 即时通信 IM 团队反馈，我们会评估是否将其加入 slice 库：
> https://console.cloud.tencent.com/workorder/category
>
> 如果您有其他功能需求，欢迎继续告诉我。
```

❌ **以下是典型违规输出，出现即视为执行错误**：

```
// 违规：读骨架文件自由实现
const msg = await chat.createCustomMessage({ payload: { data: '...' } })
await chat.sendMessage({ to: targetID, message: msg })
// → 旧 API，与 State API 架构冲突，直接导致应用崩溃
```

```
// 违规：给"仅供参考"的示例代码
// 以下是基于 SDK 通用规则的参考实现，仅供参考：
const store = useMessageInputStore(conversationID)
await store.sendMessage({ type: 'customMessage', customData: '...' })
// → 用户会直接复制使用，没有 slice 规范约束，一定会出错，导致不可用
```

## 5.4 prerequisites 链解析（A.1.5 / B.2 共用）

命中 slice 时必须递归校验 prerequisites：

```
resolveDeps(sliceId):
  slice = index[sliceId]
  for prereq in slice.prerequisites:
    if prereq in base_slices_applied + extension_slices_applied + currentBatch:
      continue   // 已满足
    if prereq in index AND prereq not in base_slices_applied:
      currentBatch.unshift(prereq)  // 自动补齐前置
      resolveDeps(prereq)            // 递归
    else:
      throw 'unmet-prerequisite'

A.1.5 场景：
  - 链长 ≤ 2（命中 1 个 slice + 自动补齐 1 个前置）→ 静默补齐
  - 链长 ≥ 3 → 把整条链显式列给用户："为了实现 X，需要同时装 Y / Z，确认吗？"
                用户拒绝 → 整个意图降级到 unsupported_intents

B.2 场景：
  - 任意链长都显式列给用户确认（路径 B 是用户主动驱动，不容易因链长惊到）
```

## 5.5 命中失败的常见原因（自查清单）

dispatcher 自己使用，不是给用户看的：

- 关键词在 `trigger-keywords` 里漏列了 → 提 issue 补关键词
- 用户用的是别名（如把 "已读回执" 说成 "看过没") → 适当扩词
- 用户描述的是组合场景（如 "群里发订单") → 命中两个 slice，先后实现
- 场景超出当前 features 范围（如客服分配系统） → 走 §5.3 兜底
- A.1.5 阶段意图 confidence < 0.7 → 直接丢弃，不进 unsupported_intents（避免污染 session（session_context.chat））

