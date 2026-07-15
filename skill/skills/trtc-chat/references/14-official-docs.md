# 14 — 官方文档检索规则（知识咨询用）

> 本文件定义 **规则**（怎么查）。数据（URL 在哪）在 knowledge-base 的 `docs/chat/` 下（用 `tools.kb resolve`，见 `08-state-config.md` §8.0）。
> 各类型对应文档文件：
> - SDK 知识：`docs/sdk/{platform}/index.md`（需平台探测）
> - TUIKit 知识：`docs/uikit/{platform}/index.md`（需平台探测）
> - 产品计费与配置：`docs/product.md`（无需平台）
> - 服务端 REST API：`docs/restapi.md`（无需平台）
> - 服务端回调：`docs/webhook.md`（无需平台）

---

## 14.1 platform → 文档路径映射（SDK 与 TUIKit 类型需要）

> platform 由 D.2 已探测完毕。仅 SDK 知识（D-e）与 TUIKit 知识（D-d）类型需要此映射。

### SDK 映射
- `platform = "web" / "miniprogram" → Bash `python3 -m tools.kb resolve docs/chat/sdk/web/index.md` → Read 输出路径`
- `platform = "android"           → Bash `python3 -m tools.kb resolve docs/chat/sdk/android/index.md` → Read 输出路径`
- `platform = "ios"               → Bash `python3 -m tools.kb resolve docs/chat/sdk/ios/index.md` → Read 输出路径`
- `platform = "flutter"           → Bash `python3 -m tools.kb resolve docs/chat/sdk/flutter/index.md` → Read 输出路径`

### TUIKit 映射
- `platform = "android"           → Bash `python3 -m tools.kb resolve docs/chat/uikit/android/index.md` → Read 输出路径`
- `platform = "ios"               → Bash `python3 -m tools.kb resolve docs/chat/uikit/ios/index.md` → Read 输出路径`
- `platform = "android+ios"       → **分别** resolve + Read android 与 ios 两份 index（见 §14.1.1）
- `platform = "flutter"           → Bash `python3 -m tools.kb resolve docs/chat/uikit/flutter/index.md` → Read 输出路径`
- `platform = "uniapp"            → Bash `python3 -m tools.kb resolve docs/chat/uikit/uniapp/index.md` → Read 输出路径`
- `platform = "vue3"              → Bash `python3 -m tools.kb resolve docs/chat/uikit/vue3/index.md` → Read 输出路径`
- `platform = "react"             → Bash `python3 -m tools.kb resolve docs/chat/uikit/react/index.md` → Read 输出路径`

### §14.1.1 双端原生对比（`platform = "android+ios"`）

适用：用户同时问 Android **与** iOS（例：「Native Chat UIKit 是否 Android 和 iOS 各有一套原生组件」）。

```
1. resolve + Read docs/chat/uikit/android/index.md
2. resolve + Read docs/chat/uikit/ios/index.md
3. 按 14.2 分别检索两端文档（禁止用 Web TUIKit 代替）
4. 回答结构：
   ┌─ 结论：是否为各自原生组件栈（是/否 + 一句话）
   ├─ Android：组件形式 / 集成形态
   └─ iOS：组件形式 / 集成形态
```

❗ **平台锁定例外**：`android+ios` 时允许（且必须）同时检索 android 与 ios 官方文档；禁止只答一端；禁止跨到其他平台（如 web/vue3）替代。

---

## 14.2 检索策略

### 选择 web_search 还是 web_fetch

| 条件 | 方法 | 示例 |
|------|------|------|
| 问题指向明确的具体页面（docs/index.md 有直接 URL 映射） | `web_fetch` | "初始化参数有哪些" → fetch |
| 问题宽泛、不确定具体 URL，或需要跨页面综合 | `web_search` | "Web 和小程序有什么差异" → search |

### 检索指令模板

```
web_search:
  query: "腾讯云 IM {具体问题关键词} 官方文档"
  limit: 5

web_fetch:
  url: <docs/index.md 映射出的目标 URL>
  fetchInfo: "从页面中提取 {问题关键词} 相关的内容"
```

### 失败兜底

- `web_fetch` 返回空 / 404 → 降级为 `web_search` 重试
- `web_search` 返回空 → 告知用户"未检索到匹配内容，建议访问官网文档中心：`https://cloud.tencent.com/document/product/269`"
- 网络不可用 / 连续失败 → 输出软引导：

```
> 当前无法访问官网文档。建议您直接前往官网文档中心查看：
> https://cloud.tencent.com/document/product/269
>
> 或者，您可以粘贴具体报错/API 名称，我尝试基于已知知识帮您分析。
```

### 检索边界（三条红线）

❗ **平台锁定**：`web_fetch` / `web_search` 只能检索当前平台（从 D.2 获取）对应的官方文档。禁止跨平台检索。`platform = "android+ios"` 时**例外**：须同时检索 android 与 ios 两端文档。产品/服务端/回调类型不受平台锁定限制。

❗ **API 存在性判定**：用户问的 API 名称，先在对应文档中确认是否存在。若不存在 → 告知用户"当前不支持此 API"，并说明等效替代方案。

❗ **文档域限定**：检索仅限上表列出的域名。禁止检索其他域名的资料作为官方答案。

---

## 14.3 知识边界

### ✅ 属于知识咨询

- 问 SDK 集成方法、初始化参数、平台差异
- 问登录流程、UserSig 获取/刷新/验证
- 问特定 API 的入参/返回值/用法示例
- 问 SDK 版本迁移步骤、废弃 API 替代方案
- 问错误码含义、常见原因、解决方案
- 问 IM 产品计费、价格、免费额度、套餐、购买开通
- 问产品能力限制（群人数上限/消息保存时长/文件大小限制等）

### ❌ 不属于知识咨询

| 情况 | 处理 |
|------|------|
| 用户问的是本项目已有代码中的具体实现（如"登录按钮在哪"、"消息列表怎么渲染的"） | 走 C.3 追问/质疑流（读本地文件） |
| 用户报本项目编译/运行错误（如"npm run dev 报错"、"页面白屏"） | 走 C.3 报错排查流（读 `09-troubleshoot.md`） |
| 用户需要新增一个未被 slice 覆盖的 SDK 功能（如"帮我实现消息转发"且本地无对应 slice） | **阻断**：走 B.2 兜底（不可实现 + 工单引导）|

---

## 14.4 错误码匹配策略

用户说错误码时通常不说来源（SDK / 服务端）。按以下规则选择目标 URL：

> ⚠️ **编号优先原则**：错误码的路由以 **编号所在范围** 为准，而非当前 `types` 字段。
> 即使 `types=["sdk"]`，若错误码落在下方「服务端错误码」范围内，仍查 `docs/restapi.md`。
> 反之，若 `types=["restapi"]` 但错误码落在 SDK 范围（2xxx/3xxx/8xxx），仍查对应 SDK 文档。
> 这解决了「用户在 SDK 场景中遇到服务端错误码」的交叉路由问题。

**Web SDK 错误码范围（查 `docs/sdk/web/index.md` E 区）：**
- `2xxx`（2000–2999）— 登录/消息/群组/好友/网络/文件上传等核心 SDK 功能
- `3xxx`（3000–3153）— SDK not ready / 套餐 / 搜索参数
- `8xxx`（8010–8020）— 信令（邀请/取消）

**Android / iOS / Flutter SDK 错误码范围（查对应平台 `docs/sdk/{platform}/index.md` 错误码区）：**
- 各平台 SDK 错误码定义在对应平台的 index.md 中，优先读对应平台文档

**云端搜索错误码（看上下文）：**
- `27002` / `27003` / `60018` / `60020` — 如果用户输入包含"搜索/searchCloudMessages/云端搜索/云搜"等信号，说明是 SDK 搜索接口抛的，优先查 SDK 页
- 如果用户只是单纯问错误码含义（无搜索上下文），按服务端错误码处理，查 `docs/restapi.md`

**服务端错误码（查 `docs/restapi.md` 通用技术节）**

| 错误码范围 | 分类 |
|-----------|------|
| `2001` ~ `2100`、`93000` ~ `93008` | 内容审核错误码 |
| `10002` ~ `11000`、`110006` ~ `110014` | 群组错误码 |
| `20001` ~ `22007`、`90001` ~ `91101`、`120001` ~ `130000` | 消息错误码 |
| `30001` ~ `31804`、`38000` ~ `39000` | 关系链错误码 |
| `40001` ~ `40610` | 资料错误码 |
| `50001` ~ `51013` | 最近联系人错误码 |
| `60002` ~ `60028`、`80001` ~ `80005` | 后台公共错误码 |
| `70001` ~ `72012` | 账号错误码 |

**兜底策略：** 不在此规则内或上述页面未命中 → `web_search` 搜索 `"错误码 {错误码} 腾讯云 IM"`

### 检索域（按文档类型）

| 文档 | 域名 |
|------|------|
| SDK 知识（`docs/sdk/{platform}/index.md`） | `cloud.tencent.com/document/product/269` + `web.sdk.qcloud.com/im/doc/` |
| TUIKit 知识（`docs/uikit/{platform}/index.md`） | `cloud.tencent.com/document/product/269` |
| 产品计费与配置（`docs/product.md`） | `cloud.tencent.com/document/product/269` + `buy.cloud.tencent.com` |
| 服务端 REST API（`docs/restapi.md`） | `cloud.tencent.com/document/product/269` |
| 服务端回调（`docs/webhook.md`） | `cloud.tencent.com/document/product/269` |

---

## 14.5 高频问题预检

> 预检答案在 `python3 -m tools.kb resolve docs/chat/sdk/{platform}/faq.md` 中。D.4d 步骤 2 先读该文件判断是否命中预检清单。

命中 → 直接输出预检答案，不执行 `web_fetch`（FAQ 为 SDK 基础常识，变化频率低，不需要实时验证）。
未命中 → 走标准检索流程（`web_fetch` / `web_search`）。
