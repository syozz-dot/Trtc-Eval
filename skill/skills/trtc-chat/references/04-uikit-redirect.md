# 04 - UIKit 边界说明

> 策略：dispatcher 在 Step 1 探测时**不再区分** UIKit / 非 UIKit，只看项目是否依赖 `tuikit-atomicx-vue3`。
> 本文件保留为后续版本扩展位，同时提供"用户主动问"时的统一回答模板。

## 4.1 当前策略

- 检测信号：`package.json` 是否依赖 `tuikit-atomicx-vue3`
  - 有 → 路径 B（State API 增量）
  - 无 → 路径 A（0→1 装基础功能）
- 增量功能统一写在用户业务代码层，**不改任何已有组件内部**

## 4.2 用户主动问"我用 UIKit 能不能用 chat-skills"

```
> chat-skills 仅适用于**无 UI 的 State API 集成场景**。
>
> UIKit 是闭源组件库，chat-skills 无法对其组件进行功能增删改。
> 如果你的项目已使用 UIKit（chat-uikit-vue3 / chat-uikit-react 等），
> chat-skills 不适用——请直接使用 UIKit 官方文档进行扩展。
>
> 如果你不使用 UIKit，只需要在业务代码层用 State API 直接调 SDK，
> chat-skills 就是为这个场景设计的。
```

## 4.3 适用范围边界

| 场景 | chat-skills 是否适用 |
|---|---|
| 无 UI，State API 直接调 SDK | ✅ 适用 |
| 使用 UIKit（闭源组件库） | ❌ 不适用 |
| 想修改 UIKit 内部组件 | ❌ 不适用（UIKit 闭源，无法介入） |
