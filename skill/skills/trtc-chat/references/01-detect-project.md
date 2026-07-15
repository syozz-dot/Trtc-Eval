# 01 - 探测项目现状（详细版）

> dispatcher Step 1 的完整脚本。被 `SKILL.md` 在探测开始时主动 `read_file`。

## 目标

读取 4 类信号，决定走路径 A 还是路径 B：

1. 集成信号（唯一基准：是否依赖 `tuikit-atomicx-vue3`）
2. Platform / 框架
3. 项目风格
4. 上次会话记忆（`.trtc-session.yaml`（经 `tools.session`），`<projectRoot>` 由 `08-state-config.md` § 8.1.1 找根算法决定，**不是** `process.cwd()`）

---

## 1. 空目录 / 新建项目识别

> 在跑 1.1 之前先做这一步，命中即走"新建项目引导"分支。

判定条件（任一满足即视为空目录 / 新建项目）：

- 当前目录无 `package.json`
- 有 `package.json` 但 `dependencies + devDependencies` 完全为空
- 仅有 `README.md / .git / .gitignore` 等少量元文件，无 `src/` 等业务代码

命中后给出新建项目引导话术：

> "我看到这是个空目录 / 新项目。chat-skills 推荐 Vue 3 + State API 方案。我可以帮你：
>
> 1. 用 Vite 起一个 Vue 3 + TypeScript 工程
> 2. 安装 `tuikit-atomicx-vue3`（State API 模式）
> 3. 默认装 Tailwind CSS 作为样式方案（如不需要请告诉我）
> 4. 按基础功能生成最小可跑的 IM 页面
>
> 是否继续？（默认 Vue 3 + State API + Tailwind）"

- 同意 → 走路径 A，按 vue3 + State API 默认链路
- 拒绝 / 想用其他 platform → 提示 当前仅 vue3，退出，不替用户做选择
- 仅"不要 Tailwind"（platform 仍用 vue3）→ 走路径 A，但在 `02-path-a-script.md` § A.3.0.1 跳过 Tailwind 装载，按用户指定的 CSS 方案走

---

## 2. 集成信号探测（口径）

读 `package.json` 的 `dependencies + devDependencies`，**只看一个信号：是否有 `tuikit-atomicx-vue3`**。

| 命中 | 判定 | 走向 |
|---|---|---|
| 依赖含 `tuikit-atomicx-vue3` | 已集成 → State API 增量 | 路径 B |
| 不含 `tuikit-atomicx-vue3`，但目录非空 | 未集成 | 路径 A |
| 空目录 / 新项目 | 未集成 | 路径 A（先经过 § 1 的新建引导） |

> 不区分 UIKit，`tuikit-atomicx-vue3` 存在即可在业务层用 State API 直接调。

❗ **不论空目录还是非空目录，只要走路径 A 且项目无已有 CSS 方案，进入 A.3 之前都按 `02-path-a-script.md § A.3.0.1` 装 Tailwind**。已有 CSS 方案的项目直接复用，不叠加。

---

## 3. Platform / 框架探测

| 探针 | 判定 |
|---|---|
| `package.json` deps: `vue` / `vite` | vue3 ✅（支持） |
| `package.json` deps: `react` / `next` | react ⏳（暂不支持） |
| `Podfile` / `*.xcodeproj` | ios ⏳ |
| `build.gradle` / `settings.gradle` | android ⏳ |
| `pubspec.yaml` 含 `flutter:` | flutter ⏳ |
| 探测无果 | AskUserQuestion 单选 |

非 vue3 项目的友好提示：

> "我看到你这是 React 项目。chat-skills 当前只支持 Vue 3，React 版本预计在 v1.1 上线。你可以：
> 1. 关注 `@tencent-rtc/trtc-agent-skills` 后续版本
> 2. 提需求到 [issue 链接]
> 3. 临时基于 `_shared/auth/` 等通用规则手动集成"

---

## 4. 项目 CSS 方案识别

> 完整流程见 `python3 -m tools.kb resolve slices/chat/web/detect-style.md`（CSS 方案 + UI 库 + 可复用组件 + 命名约定）。
> 本节只列 detect-style 未覆盖的补充探测。

### 命名约定

- 扫 `src/components/*` 的命名（kebab-case / PascalCase）
- 扫 `<script setup>` vs Options API（vue3）
- TypeScript / JavaScript

---

## 5. 上次会话记忆

读 `.trtc-session.yaml`（经 `tools.session`）（详见 `08-state-config.md`，特别是 § 8.1.1 找根算法——dispatcher 在本步骤前必须先跑一次找根并把结果缓存到当前会话）：

- 上次确认的 `platform / integration_mode / sdk_version`
- 已完成的 slice 列表
- 上次改动的文件清单

存在 → 在 项目概况反馈 时一并展示，避免重复探测/询问。

---

## 6. 探测输出（物理落盘）

> ❗ 项目画像**不能只存在上下文里**——随着代码生成占满 token，早期探测结果会被挤到 context 远端。跨对话更是完全丢失。
>
> 解决方案：**物理落盘（跨对话持久化）**。

### 6.1 物理落盘（写入 `.trtc-session.yaml` + `session（session_context.chat）`）

探测完成后，将项目画像写入 `.trtc-session.yaml`（经 `tools.session`）（schema 见 `08-state-config.md`）。

**字段**：

| 部分 | 字段 | 权威定义 |
|---|---|---|
| 入口模式 | `chatMode` / `directChatConfig` | `02-path-a-script.md` A.1 模式确认 |
| CSS 方案 | `css_scheme` / `ui_library` / `reusable_components` | `python3 -m tools.kb resolve slices/chat/web/detect-style.md` |
| 基础画像 | `integration_mode` / `platform` / `naming` / `script_style` | 本文件 § 2–4 |
| 代码进度 | `base_slices_applied` / `extension_slices_applied` / `unsupported_intents` / `changes` | `02-path-a-script.md` A.3 后 / `03-path-b-script.md` B.5 |

**落盘时机**：
- **.trtc-session.yaml**（CSS 方案 / UI 库 / 可复用组件）：A.1 结束后立即落盘
- **session（session_context.chat）**（代码进度）：A.3 + A.3.x 全部完成后统一写（见 `02-path-a-script.md` A.3 后"统一写 session（session_context.chat）"）
- 路径 B：B.5 写入代码进度

### 6.2 恢复流程（新对话 / 跨对话）

```
新对话开始 → read_file .trtc-session.yaml + session（session_context.chat）
  ├─ 有 css_scheme / ui_library? → 直接用，在 B.1 项目概况反馈 复述确认
  └─ 没有 → 按 detect-style.md 重新检测 → 落盘
```

这份画像在路径 A 的 A.1 / 路径 B 的 B.1 都会被复述给用户。
