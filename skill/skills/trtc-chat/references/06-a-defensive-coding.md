# 06-a - 防御编程统一规范

> 所有 slice 的 API 调用必须遵循本文件规范。dispatcher 写代码前与 `06-hard-rules.md` 并行 `read_file`。

---

## 6a.1 异步 API 调用范式

所有 SDK 异步调用必须遵循以下模板：

```ts
import { formatError } from '@/im/error-map'

const loading = ref(false)

async function handleAction() {
  loading.value = true
  try {
    await sdkApi(...)
    // 成功处理
  } catch (err: any) {
    showFeedback(formatError(err))  // 见 § 6a.3，必须给用户可见反馈
  } finally {
    loading.value = false
  }
}
```

❌ **禁止**：
- `try/finally` 无 `catch`（失败静默吞掉）
- `catch` 里只 `console.error` 不给 UI 反馈

---

## 6a.2 错误反馈形式

根据操作类型选择不同的反馈形式：

| 操作类型 | 反馈形式 | 原因 |
|---|---|---|
| **发消息** | 输入框附近就近显示小字 | 不打断输入流，用户可直接重试 |
| **加载消息/会话列表** | 列表区域内空态提示 + 重试按钮 | 不遮挡已有内容 |
| **写操作**（撤回/删除/置顶/免打扰/清空） | Toast（2-3 秒自动消失） | 轻量提示，不需要用户主动关闭 |
| **登录失败** | 就地显示错误 | 需要引导用户操作 |

❗ **有 UI 库时优先用 UI 库的 Toast/Message 组件；无 UI 库时自建最小 Toast（有 Tailwind/SCSS）或 `alert()`（空项目，标 TODO）**

### Toast / 错误提示视觉规范

- **颜色**：使用项目 error 色（UI 库的 `type="error"` / `variant="destructive"` / 红色系），不准用默认灰色或 info 色
- **显示位置**：居中或偏上（`top-center`），不准显示在底部——底部容易被输入框或 toolbar 遮挡
- **z-index**：`9999`，确保不被页面其他层遮挡
- **最大宽度**：`max-width: 360px`（或项目 Toast 组件已有的最大宽度约束，跟随项目规范）
- **文字换行**：`word-break: break-word`，不准单行溢出截断（`text-overflow: ellipsis`）——错误信息必须完整可读，不能被截断
- **自建 Toast 无 UI 库时**：
  ```css
  .toast-error {
    max-width: 360px;
    word-break: break-word;
    /* error 色跟随项目 CSS 变量或 Tailwind token */
  }
  ```

---

## 6a.3 错误信息内容

❗ **禁止把 SDK 原始错误 JSON 直接暴露给用户**

❗ **`ERROR_MAP` 和 `formatError` 必须提取为共用模块**，不准在每个组件里各自定义：

```
src/im/error-map.ts   ← 统一维护，各组件 import 使用
```

参考实现（`src/im/error-map.ts`）：

```ts
const ERROR_MAP: Record<number, string> = {
  20003: '对方账号不存在，请确认 userID 是否正确；可先用该 userID 登录一次，或在腾讯云 IM 控制台手动创建',
  70001: '登录凭证已过期，请重新生成 UserSig 后再登录',
  70003: '登录凭证解析失败，请使用官网提供的 API 重新生成 UserSig',
  70009: 'UserSig 验证失败，请检查请求的 SDKAppID 和生成 UserSig 的密钥或私钥是否一致',
  70013: '请求的 UserID 与生成 UserSig 时使用的 UserID 不一致，可使用 IM 控制台 UserSig 生成&校验工具校验',
  70014: '请求的 SDKAppID 与生成 UserSig 时使用的 SDKAppID 不一致，可使用 IM 控制台 UserSig 生成&校验工具校验',
  10015: '群组不存在或已经被解散，请确认群组 ID 是否正确',
  2501:  '对方账号不存在，请确认 userID 是否正确；可先用该 userID 登录一次，或在腾讯云 IM 控制台手动创建',
  2801:  '网络请求超时，请检查网络连接',
}

export function formatError(err: any): string {
  const code = err?.code
  return ERROR_MAP[code] ?? err?.errorMessage ?? '操作失败，请稍后重试'
}
```

> `error.errorMessage` 是 SDK 返回的错误描述字段，比 `err.message`（JS 原生 Error）更准确。优先用映射表，映射表未覆盖时才降级显示 `errorMessage`。

各组件使用方式：

```ts
import { formatError } from '@/im/error-map'

} catch (err: any) {
  showFeedback(formatError(err))
}
```

---

## 6a.4 状态锁规则

状态锁用于表达 loading 态（禁用按钮、显示加载中），必须在 `finally` 里复位：

| 操作类型 | 锁变量命名 |
|---|---|
| 发消息 | `sending` |
| 加载列表/消息 | `loading` / `loadingOlder` |
| 登录/登出 | `loggingIn` |
| 写操作（撤回/删除等） | `submitting` / `loading` |

❗ 状态锁必须在 `finally` 里复位，不能在 `try` 里复位（catch 路径会跳过）

---

## 6a.5 入参校验规则

以下情况必须做入参校验，不满足条件直接 `return`（不发请求）：

| 参数 | 校验条件 |
|---|---|
| 文本消息内容 | `text.trim().length > 0` |
| userID | 非空字符串 |
| conversationID | 非空字符串 |
| 文件大小 | 图片 ≤ 20MB / 视频 ≤ 100MB / 文件 ≤ 100MB |

❌ **禁止**：空 userID / 空文本直接发请求（会触发 SDK 报错，体验差且浪费请求）

> ❗ **调用顺序约束**（发消息前必须等 login resolve）见 `06-hard-rules.md § 6.1`。
