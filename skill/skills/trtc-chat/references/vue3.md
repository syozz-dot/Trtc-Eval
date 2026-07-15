---
name: trtc-chat-vue3
description: TRTC Chat Vue 3 platform pattern — 提供 vue3 + State API 的目录约定、依赖、入口骨架。dispatcher 探测到 vue3 项目时与 SKILL.md 一并加载。
applies-to: vue3
sdk-version: "tuikit-atomicx-vue3 >=6.0.0"
version: 1.0.7
---

# TRTC Chat — Vue 3 Platform Pattern

> 由 dispatcher（`SKILL.md`）在探测到 `vue3` 项目时附加加载。仅承载 vue3 特有的目录约定 / 依赖 / 入口骨架，不重复 dispatcher 的流程。

## 适用范围

- Vue 3 (Composition API，建议 `<script setup>`)
- Vite 4+ / 其他打包工具（Webpack 5、Rsbuild 等也兼容）
- TypeScript 优先；JavaScript 项目同理（需要在生成代码时去掉类型声明）

## 1. 依赖

### 1.1 安装

```bash
npm install tuikit-atomicx-vue3@latest
```

```jsonc
{
  "dependencies": {
    "tuikit-atomicx-vue3": "^6.0.0"
  }
}
```

### 1.2 硬规则

1. **Store hooks 和类型统一从 `tuikit-atomicx-vue3` 引**
   - ✅ `import { useLoginStore } from 'tuikit-atomicx-vue3/chat'`
   - ✅ `import type { ConversationInfo } from 'tuikit-atomicx-vue3/chat'`
2. **路径 B 不动用户已有依赖**：项目已安装 `tuikit-atomicx-vue3` 即视为已就位

### 1.3 状态管理

不主动添加 vuex / pinia / vue-router 等。`tuikit-atomicx-vue3` 自带 `useXxxStore` 系列 hook（`useLoginStore` / `useConversationListStore` / `useMessageListStore` / `useMessageInputStore` 等），slice 直接消费这些 hook，不再额外引状态库。如项目已有 pinia/vuex，按现有方式接入；如未有，直接用各 `useXxxStore` + `ref` / `reactive` 局部状态。

## 2. 目录约定

dispatcher 写代码时按以下结构落盘：

```
src/
├── im/
│   ├── init.ts                  # 创建 chat 实例 + login（路径 A 由 login-auth slice 生成）
│   ├── events.ts                # SDK 事件订阅（消息接收 / 会话更新等）
│   └── messages/
│       ├── order.ts             # send-custom-message slice（业务类型: 订单 → businessID = "order"，团队有命名空间约定就跟随）
│       └── ...                  # 其他业务自定义消息（rating / coupon / red-packet / vote 等；文本发送的代码归属 MessageInput.vue 组件本身，不另起文件）
├── views/
│   └── Login.vue                # login-auth slice §8（仅路径 A 生成；路径 B 不生成）
└── components/
    └── chat/
        ├── ChatPage.vue         # 聊天页面入口（路径 A 默认放在 /chat 路由）
        ├── ConversationList.vue # 含头像默认渲染规则（avatar → 字母头像 fallback）
        ├── MessageList.vue
        ├── MessageInput.vue     # 默认 toolbar；toolbar 不挂任何业务按钮，仅留扩展位
        └── bubbles/             # 业务卡片渲染组件，由 send-custom-message slice 命中时按需追加
            ├── OrderCardBubble.vue       # （示例：业务命中时生成）
            ├── RatingCardBubble.vue      # （示例：业务命中时生成，businessID = "rating"）
            └── ...
```

> 项目已有自己的 `src/api/` `src/store/` 等结构 → 优先复用 / 跟随现有约定，不强推上面的目录。
> `bubbles/` 子目录在路径 A 基础 4 件套阶段**不生成**（基础包不渲染任何业务卡片）；当 A.1.5 命中 `send-custom-message`（如订单 / 评价）或路径 B 后续需求进入时按需创建。

## 3. 入口骨架

> 见 `python3 -m tools.kb resolve slices/chat/web/login-auth.md` §7 参考实现。
> 凭据获取（SDKAppID + UserSig）见 `python3 -m tools.kb resolve docs/chat/gen-usersig.md`（`index.html` 加 `<script>` + `window.genTestUserSig`）。

## 4. SDK 事件监听

> Store（`useLoginStore` / `useConversationListStore` / `useMessageListStore` 等）已自动同步 SDK 事件，不需要手动 `chat.on(...)`。
> 各 slice 的 §3 SDK API 是唯一真理，不要在本文件找事件监听代码。

## 5. 消息列表渲染

> 见 `python3 -m tools.kb resolve slices/chat/web/message-list.md` §7 参考实现。

## 6. 与 dispatcher 的协作约定

- dispatcher 在 Step 1 探测到 vue3 项目时**附加加载本文件**
- 写代码时按本文件的目录约定落盘，具体实现以各 slice §7 参考实现为准
- 不重复 dispatcher 的流程（路径 A / B 脚本仍以 `references/02 / 03` 为准）
- 路径 B 项目里入口已有 → **不**覆盖，仅追加新增文件

## 7. 与 slice 的协作约定

- slice 内的"§ 7 参考实现"会用 vue3 + State API 写最简代码
- 平台特有的细节（如 vite 环境变量前缀 `VITE_*`）不在 slice 里重复，由本 pattern 统一约定
- slice 内的 SDK API 调用方式是绝对真理，本 pattern 不覆盖

---

> 后续 platform（react / ios / android / flutter）会在本目录平级加 `react/SKILL.md` 等，沿用相同结构。
