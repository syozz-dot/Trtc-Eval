# 11 - 集成指引模板（A.4 / B.5 时读取生成）

> AI 在 A.4 或 B.5 收尾时 `read_file` 本文件，按下方模板 + 拼装规则生成 `<projectRoot>/WHAT-TO-DO-NEXT.md`。
>
> 核心原则：**这是"施工图"不是"菜单"**——直接给当前架构的唯一最优解，不把决策负担丢回给用户。

## 拼装规则

| 条件 | 输出章节 |
|---|---|
| 总是 | § 1 改动总览 |
| 总是 | § 2 【必做】UserSig 后端签发 |
| `chatMode === "direct"` + `entryPosition in [route, footer-button]` | § 3 【可选】动态切换对话对象（路由参数版） |
| `chatMode === "direct"` + `entryPosition in [floating, sidebar]` | § 3 【可选】动态切换对话对象（组件 props 版） |
| 本次实现了 `send-custom-message` | § 4 【可选】自定义消息后端对接 |

- ❗ **闭合原则**：只输出上表命中的章节，不准追加模板未定义的内容（如"启动项目"/"快速开始"/"FAQ"/"常见问题"等）。需要告诉用户的额外信息放在 agent 回复的口头话术里，不写入文件。

## 占位符（从当前会话 Step 5 记账数据取值）

| 占位符 | 来源 |
|---|---|
| `{文件清单}` | session（session_context.chat）.changes |
| `{login 文件路径}` | login-auth 轮产出的文件路径 |
| `{targetID}` / `{targetType}` | `directChatConfig` |
| `{direct-chat-entry 文件路径}` | direct-chat-entry 轮产出的文件路径 |
| `{router 文件路径}` | 项目的 router 配置文件（探测阶段已知） |
| `{当前路由 path}` | 本次注册的路由 path（如 `/customer-service`） |
| `{组件名}` | 路由组件名（如 `CustomerService`） |
| `{实际 businessID}` | send-custom-message 轮写入的 businessID |
| `{实际字段列表}` | 生成的 `customData` 结构体字段 |
| `{parse 函数所在文件路径}` | message-list 中 Custom 分支位置 |
| `{Bubble 组件文件路径}` | 本次生成的卡片组件 |
| `{父组件文件路径}` | 处理卡片点击的父组件 |
| `{按钮文案}` | 卡片上实际生成的操作按钮文案（如"确认收货"/"立即领取"） |
| `{操作标识}` | 按钮对应的 action 字符串（如 `confirm_received`） |
| `{关键业务ID}` | 该卡片的主键字段名（如 `orderId` / `couponId`） |
| `{业务路径}` | 建议的后端接口路径（如 `orders/confirm`） |

---

## 模板（整体输出到 WHAT-TO-DO-NEXT.md）

```markdown
# 接下来要做的事

> chat-skills 已完成 Chat 集成，以下是改动说明和上线前的对接事项。

---

## 1. 改动总览

| 文件 | 用途 |
|---|---|
| {文件清单} |

---

## 2. 【必做】上线前切换 UserSig 签发方式

当前代码使用 `public/debug/` 目录中的 SecretKey **在前端本地生成** UserSig（仅开发期），**上线前必须切换为后端动态签发**。

> ⚠️ SecretKey 暴露在前端意味着任何人都能伪造身份登录，这是严重安全隐患。

### 上线前必做清单

1. 后端实现 UserSig 签发接口（官方文档：https://cloud.tencent.com/document/product/269/32688 ，提供 Java / Go / Python / Node.js 示例）
2. 在 `{login 文件路径}` 中填入后端接口地址（见下方）
3. 删除整个 `public/debug/` 目录

### 前端替换位置

文件：`{login 文件路径}`

```ts
// 替换前（开发期 —— 本地生成）：
const TOKEN_ENDPOINT = ''

// 替换后（生产期 —— 填入后端接口地址）：
const TOKEN_ENDPOINT = 'https://your-backend.com/api/im/get-user-sig'
```

填入地址后，`resolveCredentials` 自动走后端分支。再删除 `public/debug/` 目录即完成切换。

---

[仅 chatMode === "direct" + entryPosition in [route, footer-button] 时输出]
## 3. 【可选】动态切换对话对象

当前固定对话对象：`{targetID}`（类型：{targetType}），写死在入口组件顶部常量 `TARGET_ID` 中（见 `{direct-chat-entry 文件路径}` 文件顶部）。

如果需要动态切换（如不同商品咨询不同卖家），按以下 3 步改造：

### 第 1 步：改路由配置

文件：`{router 文件路径}`

```js
// 改前
{ path: '{当前路由 path}', component: {组件名} }

// 改后
{ path: '{当前路由 path}/:targetID', component: {组件名} }
```

### 第 2 步：页面组件从路由取参数

文件：`{direct-chat-entry 文件路径}`

```js
import { useRoute } from 'vue-router'

const route = useRoute()
const targetID = route.params.targetID || import.meta.env.VITE_TRTC_CHAT_TARGET_ID
const conversationID = `{targetType}${targetID}`
```

### 第 3 步：入口处传参

```vue
<RouterLink :to="`{当前路由 path}/${你的业务变量}`">咨询客服</RouterLink>

<!-- 不传参时走 .env.local 默认值 -->
<RouterLink to="{当前路由 path}">在线客服</RouterLink>
```

### 群聊场景

如果对话对象是群（如客服组），改 conversationID 前缀：
```js
const conversationID = `GROUP${targetID}`
```

---

[仅 chatMode === "direct" + entryPosition in [floating, sidebar] 时输出]
## 3. 【可选】动态切换对话对象

当前固定对话对象：`{targetID}`（类型：{targetType}），写死在入口组件顶部常量 `TARGET_ID` 中（见 `{direct-chat-entry 文件路径}` 文件顶部）。

如果需要动态切换，改以下 2 步：

### 第 1 步：给组件添加 prop

文件：`{direct-chat-entry 文件路径}`

```js
const props = defineProps({
  targetID: { type: String, default: '' }
})

const finalTargetID = props.targetID || import.meta.env.VITE_TRTC_CHAT_TARGET_ID
const conversationID = `{targetType}${finalTargetID}`
```

### 第 2 步：父组件传参

```vue
<CustomerServicePanel :targetID="shopOwnerID" @close="visible = false" />
```

---

[仅实现了 send-custom-message 时输出]
## 4. 【可选】自定义消息后端对接

### 4.1 前端消息结构体（customData 内容）

```json
{
  "businessID": "{实际 businessID}",
  "version": 1,
  "data": {
    {实际字段列表}
  }
}
```

该结构 `JSON.stringify` 后放入 `customData` 字段发送。

### 4.2 前端渲染逻辑

解析位置：`{parse 函数所在文件路径}`

```
收到消息 → messageType === MessageType.Custom
  → JSON.parse(messagePayload.customData)
  → 校验 businessID === '{实际 businessID}'
  → 渲染卡片组件：{Bubble 组件文件路径}
```

### 4.3 服务端发送（REST API）

当后台需要主动推送该消息时（如订单状态变更、系统推送优惠券）：

- 单聊：https://cloud.tencent.com/document/product/269/2282
- 群聊：https://cloud.tencent.com/document/product/269/1629
- 消息格式：https://cloud.tencent.com/document/product/269/2720

请求体示例：

```json
{
  "SyncOtherMachine": 1,
  "From_Account": "system",
  "To_Account": "{接收方 userID}",
  "MsgRandom": 1234567,
  "MsgBody": [{
    "MsgType": "TIMCustomElem",
    "MsgContent": {
      "Data": "{4.1 结构体 JSON.stringify 后的字符串}",
      "Desc": "{description 文案}",
      "Ext": ""
    }
  }]
}
```

> ⚠️ `Data` 是字符串，需要将 4.1 结构体 stringify 后放入。

### 4.4 卡片操作对接业务系统

> 以下按本次生成的卡片**实际操作按钮**逐个输出对接协议。每个操作是一条完整链路：前端点击 → 调你的后端 → 后端处理 → 推状态更新消息。
> ❗ skill 不写你的后端业务代码，但会告诉你：接口长什么样、前端怎么调、调完消息怎么更新。

[对卡片的每个操作按钮，重复输出以下结构]

#### 操作：{按钮文案}（如"确认收货" / "立即领取" / "提交评分"）

**完整链路**：

```
用户点击卡片"{按钮文案}"
  → 前端调你的后端接口（① 定义）
  → 你的后端处理业务逻辑（你自己实现）
  → 后端通过消息修改 API 更新原卡片状态（③ 格式）
  → SDK messageList 自动更新，卡片响应式刷新
```

**① 你的后端需要提供的接口**（建议结构，按实际调整）：

```
POST /api/{业务路径}
Request:  { {关键业务ID}: string, action: "{操作标识}", operatorID: string }
Response: { success: boolean, newStatus?: string, message?: string }
```

**② 前端调用位置**（已生成骨架，含 TODO 标记）：

文件：`{父组件文件路径}`

```ts
async function onCardAction(payload) {
  if (payload.action === '{操作标识}') {
    // TODO: 替换为你的真实接口地址
    const res = await fetch('/api/{业务路径}', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        {关键业务ID}: payload.data.{关键业务ID},
        action: '{操作标识}',
        operatorID: currentUser.id, // 当前登录 IM 的 userID（从 useLoginStore().loginUserInfo 取）
      }),
    })
    if (!res.ok) { /* 提示操作失败 */ }
    // 不需要手动更新卡片——后端推的新消息会自动刷新状态
  }
}
```

**③ 后端操作完成后，修改原消息更新卡片状态**：

用消息修改 REST API 将原卡片的 `Data` 字段更新为新状态：

- 修改单聊消息：https://cloud.tencent.com/document/product/269/74740
- 修改群聊消息：https://cloud.tencent.com/document/product/269/74741

**单聊**（通过 `MsgKey` 定位，格式：`clientSeq_random_serverTime`）：

```json
{
  "From_Account": "{发送方 userID}",
  "To_Account": "{接收方 userID}",
  "MsgKey": "{发送卡片时服务端返回的 MsgKey}",
  "MsgBody": [{
    "MsgType": "TIMCustomElem",
    "MsgContent": {
      "Data": "{businessID + 更新后的 data，如 status: received}",
      "Desc": "{更新后的描述文案}"
    }
  }]
}
```

**群聊**（通过 `GroupId` + `MsgSeq` 定位）：

```json
{
  "GroupId": "{群 ID}",
  "MsgSeq": {发送卡片时服务端返回的 MsgSeq},
  "MsgBody": [{
    "MsgType": "TIMCustomElem",
    "MsgContent": {
      "Data": "{businessID + 更新后的 data}",
      "Desc": "{更新后的描述文案}"
    }
  }]
}
```

> ⚠️ 消息标识（`MsgKey` / `MsgSeq`）由**后端在发送卡片时记录**（发送接口的响应会返回）。前端不需要存这些值——前端只负责把业务 ID（如 `orderId`）传给后端，后端根据业务 ID 查到对应的消息标识再调修改接口。
>
> **如果卡片是前端发送的**（非后端主动推），后端获取消息标识有两种方式：
> - **方式 1（推荐）：配置发送后回调**——IM 服务端在消息发出后，将完整消息（含 `MsgKey`/`MsgSeq`）回调到你的后端 URL。后端解析 `customData` 中的 `businessID` + 业务 ID，存下映射关系。
>   - 单聊回调：https://cloud.tencent.com/document/product/269/2716
>   - 群聊回调：https://cloud.tencent.com/document/product/269/2661
> - **方式 2：前端发送成功后上报**——`sendMessage` 成功后从返回的消息体中取 `clientSequence` / `random` / `serverTime`（单聊拼成 `MsgKey`）或 `sequence`（群聊即 `MsgSeq`），调后端接口上报存储。

**④ 前端卡片状态刷新机制**：

后端修改消息后，SDK 的 `messageList` 会自动更新对应消息的内容。前端不需要额外处理——卡片组件从 `msg.messagePayload.customData` 读取 `status` 字段，响应式自动刷新渲染。

[如果卡片只有"查看详情"这种纯前端跳转操作，则不输出上述 ①②③④，只输出：]

#### 操作：{按钮文案}（如"查看详情"）

纯前端行为，不涉及后端调用：

```ts
// 文件：{父组件文件路径}
function onCardAction(payload) {
  if (payload.action === 'view_detail') {
    router.push(`/your-page/${payload.data.{关键业务ID}}`)
    // 或：打开 Dialog 展示详情
  }
}
```
```
