# 12 - 页面组合约束（Page Composition Rules）

> 当多个 slice 产物需要在同一个父组件中协作时，AI 按本文件对应场景的约束生成胶水层代码。
>
> 设计原则：每个场景给出**状态中转机制 + 接线规则 + 布局 + 禁止项**四段式约束，收敛为唯一解，消除 AI 自由推断空间。

---

## 场景 1：Full Chat 主页（ChatPage）

**触发条件**：`chatMode === "full"`，A.3 轮次 2-4 完成后组合。

### 状态中转
- ❗ `currentConversationID` 用 `ref('')` 声明在 ChatPage 内部
- ❗ 不准用 pinia/vuex store、route params、provide/inject
- ❗ 初始值空字符串，`v-if="currentConversationID"` 控制消息区显隐

### 接线规则
- ❗ ConversationList `@select="handleSelect"`（handleSelect 同时更新 currentConversationID + currentConv，见 ChatHeader 节）
- ❗ MessageList `:conversationID="currentConversationID"` + `:key="currentConversationID"`
- ❗ MessageInput `:conversationID="currentConversationID"` + `:key="'mi-' + currentConversationID"`
- ❗ 所有接收 `conversationID` 作为 props 并在 setup 顶层调用 `useXxxStore(props.conversationID)` 的子组件，**必须**加 `:key` 确保切换会话时销毁重建
  - ❌ `<MessageInput :conversationID="currentConversationID" />`（无 `:key`，切换会话时 store 实例不更新）
  - ✅ `<MessageInput :conversationID="currentConversationID" :key="'mi-' + currentConversationID" />`
  - 原理：`useXxxStore(id)` 在 `<script setup>` 顶层只执行一次，props 变化不会重新创建 store 实例；必须靠 `:key` 变化触发组件销毁→重建→重新执行 setup

### ChatHeader（消息区顶部）
- ❗ 消息区（MessageList + MessageInput）上方必须有 ChatHeader
- ❗ 数据来源：选中会话时调 `getConversationInfo(id)` 拉取 `ConversationInfo`，存入 `currentConv`
  ```ts
  const currentConversationID = ref('')
  const currentConv = ref<ConversationInfo | null>(null)

  const { getConversationInfo } = useConversationListStore()

  async function handleSelect(id: string) {
    currentConversationID.value = id
    currentConv.value = await getConversationInfo(id)
  }
  ```
- ❗ ConversationList 的 `@select` 改为绑定 `handleSelect`（替换原来的内联赋值）
- ❗ 必须显示：会话名称（`currentConv?.title ?? currentConversationID`）
- ✅ 可选显示：头像（`currentConv?.avatarURL` → 字母头像兜底）
- ❗ 头像渲染逻辑必须与 ConversationList 保持一致——抽取公共函数（如 `getAvatarFallback`），不重复实现
  - ❌ ChatHeader 另写一套头像兜底逻辑（与 ConversationList 行为不一致）
- ❗ ChatHeader 无需 `:key`（它自身不持有 store，数据通过 `currentConv` 传入）

### 布局（参考值）
- ❗ **外层布局必须遵循 style-guide.md §6.1 容器浮层化**：
  - 页面底色：`bg-gradient-to-br from-surface-50 to-surface-100`（微渐变灰蓝）
  - 主容器：`bg-white rounded-2xl shadow-card`（从底色浮起）
  - 页面 padding：≥ `p-4`（16px），不准贴边
  - ❌ 白底贴白底（页面和容器同色，无层次感）
- 桌面：左侧 ConversationList（推荐 300-360px）+ 右侧消息区（flex-1）
- 移动端 < 640px：全屏切换（列表 ↔ 对话），不做侧边栏

### 禁止
- ❌ ConversationList 和 MessageList 合并到同一组件
- ❌ 用全局 store 传 conversationID
- ❌ 用 route params 传（Full Chat 不需要路由切换会话）
- ❌ 接收 `conversationID` 并在 setup 顶层调用 `useXxxStore(id)` 的子组件不加 `:key`（切换会话时 store 实例不更新）

---

<!-- 
## 场景 2：群组管理页（GroupPage）
触发条件：待定
TODO: 群组管理 slice 就绪后补充

## 场景 3：联系人/好友列表页（ContactPage）
触发条件：待定
TODO: 联系人 slice 就绪后补充
-->
