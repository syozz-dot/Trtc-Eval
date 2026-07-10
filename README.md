# TRTC Skill Eval

**TRTC agent-skills 多 IDE 评测系统**。CI 全程零 API key。

---

## 这个仓库回答什么问题

| 问题 | Phase | 怎么答 |
|---|---|---|
| skill 装得对吗？ | **P1** — 装齐检查 | 4 家 IDE 目录里的资产文件是否全在正确位置 |
| skill 用得对吗？ | **P2** — 行为评测 | 跑真实 prompt，观察路由 / hooks / 工具调用是否符合预期 |
| skill 内部契约守住了吗？ | **P3** — 白盒 trace（可选）| 读 `~/.cache/trtc-traces/` 里的事件流，断言"AI 真读了某文件 / hook 没 fail_open" |

---

## 我要做什么？

### 🚀 我是新人 · 想跑通第一份报告

看 [`SOP.md · 新人上手`](./SOP.md#1-新人上手)（15 分钟从 clone 到出报告）。

### 🔧 我改了 skill · 想验证有没有回归

看 [`SOP.md · 日常流程`](./SOP.md#2-日常流程每-pr)。**核心 5 步**：

```
改 skill/case → 本地跑 P2 → 提 PR → CI 自动打分 → 报告贴回 PR 评论
```

关键：**P2 走本地个人 Pro 订阅额度（免费），只提交结果文件进 PR，CI 不调 LLM。**

### 📦 我准备发新版 · 想跑完整回归

看 [`SOP.md · 发版前完整回归`](./SOP.md#3-发版前完整回归)（4 IDE × 10 case 本地并行，60-90 分钟）。

### 🛠 我要加 case / 加 IDE / 换 fixture

看 [`SOP.md · 维护 / 重装场景`](./SOP.md#4-维护--重装场景)。

### 🔬 我想加白盒 trace 断言（Phase 3）

看 [`SOP.md · 附录 A · Phase 3`](./SOP.md#附录-a--phase-3-白盒-trace-评测)。用 `python3 run_eval.py --with-trace ...` 激活。

---

## CI 结构

4 份 workflow，**没有一份需要 API key**：

| Workflow | 触发 | 干什么 |
|---|---|---|
| `skill-check-install.yml` | 每 PR · 每天 03:07 UTC | P1 装齐检查（4 IDE 并行） |
| `parser-regression.yml` | 每 PR | 8 fixture 回归 + 敏感信息扫描 |
| `skill-eval-p2-score.yml` | PR 里 `eval-runs/**/results.*.yaml` 变更 | 打分 → 表格化报告贴 PR 评论 + Actions Job Summary |
| `skill-ci-probe.yml` | 仅手动 | 探测 IDE CLI 认证方式（研究性质） |

**跨仓联动**：agent-skills 发新版时会 dispatch 到本仓的 P1（配置在 agent-skills 那边）。此外本仓 P1 每天 03:07 UTC 自动追踪 `@latest` 变化，双保险。

---

## 详细文档

- **[`SOP.md`](./SOP.md)** — 操作 SOP，六节场景化 checklist（推荐入口）

---

## 命令速查

```sh
# 装 skill 到本目录
npx -y @tencent-rtc/trtc-agent-skills@latest add

# P1 装齐检查
python3 check_install.py --ide all

# P2 smoke（2 case FAQ，~3 分钟）
python3 run_eval.py --ide claude-code --tags smoke --out-dir eval-runs/$(date +%Y%m%d)-smoke

# P2 全量（10 case，~15 分钟）
python3 run_eval.py --ide claude-code

# 打分（本地 CLI 格式）
python3 score.py eval-runs/<date>/results.claude-code.yaml

# 打分（markdown 格式，CI 用）
python3 score.py eval-runs/<date>/results.claude-code.yaml --format markdown

# 免费额度自检（30 秒验证 CLI 事件流可解析）
python3 run_eval.py --ide cursor --probe

# Phase 3：加白盒 trace 断言（读 ~/.cache/trtc-traces/）
python3 run_eval.py --ide claude-code --case P2-DOCS-ERRCODE --with-trace

# 一键装 pre-commit hook（扫敏感信息）
./scripts/install-hooks.sh
```

更详细的命令 + 环境准备见 [`SOP.md`](./SOP.md)。
