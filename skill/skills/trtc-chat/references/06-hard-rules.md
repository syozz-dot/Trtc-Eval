# 06 - Hard rules 全量版（含反例）

> 主 SKILL.md 仅保留摘要。dispatcher 在写代码 / 自检前主动 `read_file` 本文件。首次加载后可缓存到当前会话上下文。

## 两大绝对约束（违反任一必须返工，不可跳过）

> **SDK API 正确性** 和 **视觉规范** 是同级的绝对约束，不存在"功能先跑起来、UI 后期再改"的优先级。
> - SDK API 错误 → 运行时崩溃，交付物不可用
> - 视觉规范违反 → 交付物不达标，同样视为返工

❗ **写每一个组件前**，先问自己两个问题：
1. 这个组件调用的 SDK API 是否来自 slice §3，还是从训练数据猜的？
2. 这个组件打开后视觉上是否达标？容器有没有从底色浮起？颜色是否超过 1 个主色？间距/圆角/字号是否命中锚点值？气泡圆角是否不对称？

---

## 6.1 SDK API 是绝对真理

### ❗ 不准从训练数据猜 API 名称
LLM 训练数据里有大量过期 / 错版的腾讯云 IM SDK 调用方式（如 `tim.sendMsg` 之类的旧名），**所有 SDK 调用必须从 slice 的"§ 3 SDK API 必读"段落里复制**。

❌ 反例：
```ts
// 不准这样写
tim.sendMsg({ to: 'user1', body: 'hi' });
```

✅ 正例（来自 slice）：
```ts
import { useMessageInputStore } from 'tuikit-atomicx-vue3/chat'
const { sendMessage } = useMessageInputStore(conversationID)
await sendMessage({ type: 'textMessage', text: 'hi' })
```

### ❗ payload 必须 `JSON.stringify` 后传 SDK
自定义消息的 `data` / `description` / `extension` 等字段，SDK 期望的是字符串。

❌ 反例：
```ts
chat.createCustomMessage({ payload: { data: { orderId: 1 } } }); // 直接传对象
```

✅ 正例：
```ts
chat.createCustomMessage({
  payload: {
    data: JSON.stringify({ orderId: 1 }),       // ✅ 字符串
    description: '订单卡片',
    extension: '',
  },
});
```

### ❗ businessID 必须有可读语义
- 必须与卡片业务强相关（如 `order` / `product` / `coupon` / `red-packet` / `rating`）
- 团队若有命名空间约定（如 `trtc/*` / `biz/*` / `shop/*`）→ 跟随团队约定
- ❌ 不准写 `'1'` / `'123'` / `'custom'` / `'card'` / `'msg'` 等无语义裸值
- 评价卡片不再是默认 demo（v0.2 起已并入 `send-custom-message` slice，businessID 自定义如 `rating` / `customer-rating`）

### ❗ 发送消息前必须 `await` login resolve
未登录就调 send → SDK 会抛 60016 / 60005 等。

✅ 正例：
```ts
await chat.login({ userID, userSig });   // 必须等
await chat.sendMessage(message);
```

### ❗ 不准改用户已有组件内部实现
- 一律在用户业务代码层用 State API 直接调 SDK
- 不准 `document.querySelector('.tui-chat-input')` 这类 hack 已有组件 DOM
- 不准用 `:deep(...)` 强改用户既有组件样式
- 增量功能写在自己新建的业务组件里，与项目已有组件并存（含可能存在的 UIKit）

---

## 6.2 UI 是自由的，但守 3 条底线

> 样式由 AI 自由发挥，不预设审美规则。但必须遵循项目已有 CSS 方案和 UI 库。

❗ **写任何 UI 组件代码前，必须先** Bash `python3 -m tools.kb resolve slices/chat/web/style-guide.md` → Read（用色 / 圆角 / 间距 / 视觉禁区 / 精细化手法全在里面），所有 starter / feature slice 的 UI 部分均适用。

### ❗ 必须使用项目已有 CSS 方案和 UI 库
- 探测到 Tailwind → 用 Tailwind utility，不要再引一套 CSS
- 探测到 Element Plus → 用 `<el-card>` `<el-button>`，不要手撸 div
- 探测到 shadcn → 用 `<Card>` `<Dialog>`，不要再装新 UI 库
- 空项目（无已有体系）→ 路径 A 默认装 Tailwind，AI 自由写样式

### ❗ 必须复用项目已存在的同类组件
- `src/components/ui/card.vue` 存在 → 卡片消息复用，不再新建
- `src/components/ui/dialog.vue` 存在 → 详情弹窗复用

### ❗ 必须遵循项目现有命名约定
- 文件名：跟 `src/components/*` 现有大小写一致
- 组件名：跟现有 `<script setup>` / Options API 风格一致
- TS 类型：跟现有 interface / type 命名一致

---

## 6.3 增量改动安全

### ❗ patch 文件前必须先 `read_file`
- 用户可能在你上次 read 之后改过文件
- 直接 patch 会覆盖未读到的最新改动

### ❗ 不准改用户已有的 SDK 初始化 / 登录代码
- 路径 B 项目里 `src/im/init.ts` 里的 `chat.create` / `chat.login` 已经在跑
- 增量功能必须在用户已有的 chat 实例上调 API
- 如果发现 init 写法陈旧 / 有 bug → 先告知用户，不要默默改

### ❗ Plan 阶段必须显式列出"不会改的东西"
- 这是给用户的承诺，也是 dispatcher 自己的红线
- 模板见 `03-path-b-script.md` B.4

### ❗ 写文件前必须确认改动清单（用户可打断）
- 列出所有要新增 / 修改的文件路径
- 等用户回"开始" / "调整：xxx" 再动手
- 用户说"按你判断"等同于"开始"

---

## 6.4 逐 slice 闭环 + 禁止预读（long-context 退化对策）

> 这一节 hard rules 适用于**所有**多 slice 场景：路径 A 的 A.3 基础 4 件套 + A.3.x 扩展 N 件套（N ≤ 3），以及路径 B 一次需求命中多个 slice（如"群里发订单卡片"同时命中 `group-chat` + `send-custom-message`）的情况。

### ❗ 禁止预读
- 写第 N 个 slice 时，**不准** `read_file` 第 N+1、N+2…个 slice 文件
- 不准在 Plan 阶段批量装载所有候选 slice 再回头一个个写
- 下一个 slice 必须在当前 slice 的 read → plan → write → self-check → 内部记账 5 步全部完成后再读

### ❗ 每轮闭环
每个 slice 的处理必须严格走 5 步：

```
Step 1  read_file 当前 slice 完整内容
Step 2  Plan：1-3 句告诉用户本轮要写什么 / 不会改什么
Step 3  Write：按 slice § 3 SDK API + § 4 hard rules 实现
Step 4  Self-check：对照本 slice § 反例库
Step 5  内部记账（仅当前会话上下文，不写盘）：
        - 本轮已完成 slice 名
        - 本轮新建 / 修改的文件清单
        - 用了哪些项目已有组件（供后续轮复用）
```

Self-check 不通过就在本轮内修，**不准**带着问题进入下一个 slice。

### ❗ 跨轮命名一致性
- 第 2 个 slice 起，写代码前先回看上一轮 Step 5 的"已用组件清单"
- 命名必须延续上一轮，不准每个 slice 另起一套
- 如本轮发现上一轮命名有问题 → 在本轮 Plan 里显式提出"建议把上一轮的 X 改名为 Y"，征求用户同意后改；不准默默改

### ❗ 扩展轮结构前瞻（防止"新卡片塞进旧气泡容器"）
- 扩展轮（如追加自定义卡片 Bubble / 新消息类型分支）写代码**前**，必须先 `read_file` 上一轮生成的模板文件，确认：
  1. 新组件要插入的位置——是在现有气泡容器**内部**还是**外部**？
  2. 如果自定义卡片不应套在气泡容器内，而上一轮模板没有为此预留分支出口 → 本轮 Plan 里**必须显式提出结构重构**（把新分支提到气泡容器外面），不准偷懒直接往已有容器里塞
  3. 重构范围写进 Plan 的"本轮要改的文件清单"，让用户可打断
- ❌ 反例：上一轮 `message-list` 把所有 type 统一包在 `<div class="msg-bubble">` 里，扩展轮直接在 `msg-bubble` 内部加了 `<OrderCardBubble>` 组件 → 卡片被套在气泡背景/圆角/阴影里，违反"自定义卡片不套气泡"
- ✅ 正例：扩展轮发现上一轮没有为 `MessageType.Custom` 预留"跳出气泡"的结构分支 → Plan 里写"需重构 MessageList 模板：Custom 分支提到 msg-bubble 外层" → 用户确认后再写

### 为什么这条规则存在（写给 dispatcher 自己看）

❌ **典型故障模式**（一次性批量读取 5 份 slice → 一次性生成全部代码时观察到的）：
- 写到第 4、5 个 slice 时，§ 4 hard rules 已"远离视野"，幻觉 SDK API 名 / 漏 `JSON.stringify` payload / businessID 错写成无前缀
- 不同 slice 之间组件命名不一致（`MessageBubble` vs `MsgItem` vs `ChatBubble` 同一个东西取三个名）
- 后写的覆盖前写的命名约定，需要回头返工

✅ **机制原理**：长上下文下 LLM 的 attention 对越早出现的内容衰减越严重（recency bias）。逐 slice 闭环让"当前 slice § 3 + § 4"始终是 ≤300 行内的最近上下文，attention 落在它身上；上一轮的输出通过 Step 5 的"已用组件 / token 清单"以**精炼摘要**而非"原文回滚"的方式带入下一轮，是 long-context attention dilution 的标准对策。

---

## 6.5 自检清单（写完后必走）

- [ ] 所有 `chat.createXxxMessage` / `chat.sendMessage` 调用与 slice 一致
- [ ] 所有 payload `data` 字段都 `JSON.stringify` 过
- [ ] businessID 都有可读业务语义（`order` / `coupon` / `rating` 等；团队有命名空间约定就跟随），无 `'1'` / `'custom'` / `'card'` 等裸值
- [ ] 没有引入新的 UI 库（除非 slice 明确要求）
- [ ] 没有改 `src/im/init.ts` 等已有初始化文件（除非用户明确同意）
- [ ] `.trtc-session.yaml`（经 `tools.session`） 已写入新 slice 名（写入字段：`extension_slices_applied` 追加 + `changes` append；详见 `08-state-config.md`）；`<projectRoot>` 由 `08-state-config.md` § 8.1.1 找根算法决定

---

## 6.6 引导菜单内容来源

- ❗ 只列 knowledge-base 中实际存在的 slice（以 `tools.kb resolve chat/web/index.yaml` 与 `tools.kb resolve slices/chat/web/<name>.md` 为准）
- ❗ 未命中任何 slice 的功能不出现在推荐列表中
- ❌ 根据 SDK 通用能力推测"应该有"的 feature slice
- [ ] 没有把临时 mock 接口写成永久代码（标 `// TODO: replace with real API`）
- [ ] **本轮 slice 是 read → plan → write → self-check 单轮闭环完成的**（不是把 N 个 slice 一次读完再批量写；多 slice 场景见 § 6.4）
- [ ] 所有异步 SDK 调用都有 `try/catch/finally`，`catch` 里调 `showFeedback(formatError(err))`，无静默吞错
- [ ] 错误反馈形式符合 `06-a-defensive-coding.md § 6a.2`（发消息→就近小字 / 写操作→Toast / 加载→空态+重试）
