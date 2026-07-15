# 02 - 路径 A 脚手架模板（A.3.0.0 专用）

> 仅在 `02-path-a-script.md` A.3.0.0 步骤中被 `read_file`，不提前加载。
> 探测到**空目录 / 无 `package.json`** 时才执行；已有项目直接跳过本文件。

---

## 1. 创建项目

❗ **必须**用以下命令创建项目，**禁止**手写 `package.json` / `vite.config.ts` / `tsconfig.*` / `index.html` 等脚手架文件：

```bash
# 拉取 Vue3 + TS 官方模板（支持非空目录，不影响已有 skill 产物）
npx --yes degit vitejs/vite/packages/create-vite/template-vue-ts --force

# 将 degit 生成的 _gitignore 内容追加到 .gitignore（不覆盖已有内容，保留 _gitignore 原文件）
cat _gitignore >> .gitignore 2>/dev/null

# 安装依赖
npm install
```

## 2. 补装必需依赖（一次性，不等 slice 发现再补）

```bash
# Full Chat 必需
npm install tuikit-atomicx-vue3 vue-router

# Direct Chat 必需（无需 vue-router）
npm install tuikit-atomicx-vue3
```

## 3. 配置 `@/` alias

`vite.config.ts`（**必须此时配，不等后续 slice 报错**）：

```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': resolve(__dirname, 'src') },
  },
})
```

`tsconfig.app.json`（或 `ts.trtc-session.yaml`）同步加 paths：

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  }
}
```
