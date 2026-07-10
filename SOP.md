# TRTC Skill Eval · Operations SOP

按场景组织。每节自成一份 checklist。

- **[1. 新人上手](#1-新人上手)** — clone 到跑通首个报告的路径
- **[2. 日常流程（每 PR）](#2-日常流程每-pr)** — skill 改动后本地验证 → 提 PR 拿报告
- **[3. 发版前完整回归](#3-发版前完整回归)** — 4 IDE 全量 P2、归档 baseline
- **[4. 维护 / 重装场景](#4-维护--重装场景)** — 替换 fixture、加 case、加 IDE、重装 hook、敏感命中处置
- **[5. 自动触发结构](#5-自动触发结构)** — cron / release-dispatch 怎么工作、如何调试
- **[6. 术语与快速参考](#6-术语与快速参考)**

---

## 1. 新人上手

**目标**：clone 完到看到"P1 全绿 + P2 smoke 全 Y + CI 报告"用时约 15 分钟。

### 1.1 前置

- macOS / Linux；Python 3.9+；Node 20+；`gh` CLI 已认证 `syozz-dot/Trtc-Eval` 的读写权限
- 至少一家 IDE 的 headless CLI 已登录 Pro 订阅（`claude` / `cursor-agent` / `codex` / `codebuddy` 任选一家；下面用 claude-code 举例）

### 1.2 环境准备

```sh
# clone Trtc-Eval
gh repo clone syozz-dot/Trtc-Eval ~/Desktop/Trtc-Eval-repo
cd ~/Desktop/Trtc-Eval-repo

# Python 依赖
pip install pyyaml

# 装 skill 到当前目录（每家 IDE 一份完整分发）
npx -y @tencent-rtc/trtc-agent-skills@latest add --ide all

# 装 pre-commit hook（本地就地扫敏感信息）
./scripts/install-hooks.sh
```

### 1.3 首次验证

```sh
# P1 全量资产检查（4 IDE）
python3 check_install.py --ide all
# 期望：全绿 4/4

# P2 smoke（1 家 IDE，约 3 分钟）
python3 run_eval.py --ide claude-code --tags smoke --out-dir eval-runs/$(date +%Y%m%d)-hello

# 本地打分
python3 score.py eval-runs/$(date +%Y%m%d)-hello/results.claude-code.yaml
# 期望：2 pass · 0 fail · avg_score=1.00
```

### 1.4 出问题去哪找

| 症状 | 去哪 |
|---|---|
| `command not found: claude / cursor-agent / codex / codebuddy` | 相应 IDE 的官网装 CLI |
| `No module named 'yaml'` | `pip install pyyaml` |
| P2 卡住 >2 分钟没反应 | Ctrl-C，看看 IDE 是否需要 `login` |
| `route_level1: N (expected trtc-docs, got <none>)` | 90% 概率是 dispatcher 被便宜模型绕过 — 换 sonnet/opus/gpt-4o 试试 |

---

## 2. 日常流程（每 PR）

**目标**：改了 skill / 想验证 skill 表现，5 分钟内出 PR 报告。

### 2.1 什么时候需要跑

只在**这些改动后**才需要跑 P2：

- 改了 skill 的 SKILL.md / hooks / tools / dispatcher 逻辑
- 改了 Trtc-Eval 的 case / parser / 判定器
- 想验证一个新模型 / 新 CLI 是否会绕过 dispatcher

**改文档、改脚注、改 README** 不用跑 P2 — 走普通 PR，P1 + parser 回归会自动跑。

### 2.2 单 IDE smoke（推荐）

```sh
cd ~/Desktop/Trtc-Eval-repo
git checkout -b feat/xxx
# ... 改 skill / 改 case ...

# 跑 smoke（3-5 分钟，本机 Pro 免费额度）
python3 run_eval.py --ide claude-code --tags smoke --out-dir eval-runs/$(date +%Y%m%d)-smoke

# 本地先看一眼
python3 score.py eval-runs/$(date +%Y%m%d)-smoke/results.claude-code.yaml

# results.yaml + summary.json 一起进 PR
# 注：transcripts/ 被 .gitignore 挡在外面，故意的（可能含敏感数据）
git add eval-runs/
git commit -m "eval: <what changed>"
git push origin feat/xxx
gh pr create --base main --head feat/xxx --title "..." --body "..."
```

### 2.3 看 CI 报告

PR 创建后**约 20 秒内**：

- **P2 报告**：PR conversation 底部会出现 `github-actions[bot]` 的 sticky comment，含 Case 表格、总分、和 main baseline 的 diff（如有）
- **每个 workflow 的详情**：点 checks 面板任意一条 → Job Summary 就是简化版报告
- **P1 fail**：只有 P1 fail 时才会有 P1 comment。全绿时不发（避免 comment 刷屏）

### 2.4 结果解读

| Result 列 | 含义 |
|---|---|
| ✅ pass | 全 hard 观察点 Y |
| ✅ pass (N concern) | pass，但有 N 个 `route_level1/level2` soft 观察点 N — 记录不阻塞 |
| ❌ fail | 至少一个 hard 观察点 N |
| ❌ CRITICAL | `route_triggered` N — 主 skill 根本没被激活 |
| ⚠️ incomplete | yaml 填写不完整（一般是 run_eval.py 没跑完就 Ctrl-C 的产物）|

### 2.5 常见 fail 处置

- **`route_level1: N`（soft）** — 便宜模型抄近道跳过 dispatcher。**不用改 skill**，换回 sonnet/opus 类完整推理模型
- **`reporting_called: N`（hard）** — reporting.py prompt 没被调用。检查你改的 skill 是否破坏了 `reporting.py prompt --text` 这一步的入口引用
- **`tools_called: N`（hard）** — 期望某工具（如 query_classifier / search）被调用但没有。90% 是 dispatcher 逻辑被改坏，10% 是 case 期望本身过时（改 case 而不是改 skill）

---

## 3. 发版前完整回归

**目标**：给 baseline 打一份四家 IDE × 10 P2 case 的完整快照，写进 main 供后续 PR 做 baseline diff。

### 3.1 时机

- agent-skills 仓准备发新版 npm 之前
- Trtc-Eval 本身发 v2 判定规则前
- 季度性回归（可选）

### 3.2 4 家并行本地跑

预留 60-90 分钟。建议开 4 个终端并行：

```sh
# 终端 1
python3 run_eval.py --ide claude-code --out-dir eval-runs/$(date +%Y%m%d)-release-claude-code

# 终端 2
python3 run_eval.py --ide cursor --out-dir eval-runs/$(date +%Y%m%d)-release-cursor

# 终端 3
python3 run_eval.py --ide codex --out-dir eval-runs/$(date +%Y%m%d)-release-codex

# 终端 4
python3 run_eval.py --ide codebuddy --out-dir eval-runs/$(date +%Y%m%d)-release-codebuddy
```

跑失败的话看第 1 节 "出问题去哪找"。

### 3.3 打分 + 提交

```sh
# 4 份 summary
for ide in claude-code cursor codex codebuddy; do
  python3 score.py eval-runs/$(date +%Y%m%d)-release-$ide/results.$ide.yaml
done

git checkout -b release/$(date +%Y%m%d)-full-p2
git add eval-runs/
git commit -m "eval: full P2 baseline before release $(date +%Y%m%d)"
git push origin release/$(date +%Y%m%d)-full-p2
gh pr create --base main --head release/$(date +%Y%m%d)-full-p2 \
  --title "release: full P2 baseline $(date +%Y%m%d)" \
  --body "..."
```

CI 会自动跑打分并贴报告。合入 main 后，**这份 summary.\*.json 就成了下一次 PR 的 baseline**。

### 3.4 归档

对话过程 / 决策记录 / 发现的 skill bug → `~/Desktop/cc/YYYYMMDD-<话题>.md`（本仓外的团队归档目录，格式见那边的 README）。

---

## 4. 维护 / 重装场景

### 4.1 替换 golden fixture（parser regression）

Fixture 就是"当前 parser + 判定器认为是 100% 全 Y 的样本"。**只有真跑得到全 Y 的转录才能进 fixture**。

```sh
# 1. 用真实 CLI 跑一遍（不带 --out-dir，默认写到临时目录）
python3 run_eval.py --ide cursor --tags smoke --out-dir /tmp/new-fixture-source

# 2. 确认全绿
python3 score.py /tmp/new-fixture-source/results.cursor.yaml

# 3. 覆盖到 fixtures/
cp /tmp/new-fixture-source/transcripts/P2-DOCS-*.turn1.jsonl fixtures/transcripts/cursor/

# 4. 本地跑一次回归测试，确认新 fixture 通过
python3 tests/test_parser_regression.py
# 期望：8/8 ok（或你换了多少家就多少家）
```

### 4.2 加新 case

改 `cases.json`，脚本无需动：

```json
{
  "case_id": "P2-XXX-NEWCASE",
  "phase": "p2",
  "category": "...",
  "tags": ["smoke", "..."],
  "turns": [
    {
      "prompt": "...",
      "expect": {
        "route_triggered": "trtc",
        "route_level1": {"target": "trtc-docs", "must_not": []},
        "reporting_called": {"scripts": ["reporting.py prompt"]},
        "tools_called": {...}
      }
    }
  ]
}
```

**加了新 case 后**：
- 需要给 4 IDE 分别补 fixture（跑 `run_eval.py --case P2-XXX-NEWCASE` 拿到 transcript，cp 到 `fixtures/transcripts/*/`）
- 或者暂时不加 fixture — 只 case，不进 parser regression（下次真跑时才会评估）

### 4.3 加新 IDE 支持

1. `cases.json` 顶层 `ide_profiles` 加一节（binary / args / event_dialect / capabilities）
2. 如果事件流方言跟 claude/cursor/codex 都不一样：`run_eval.py` 加 `_parse_<newide>()`（参考 `_parse_cursor()` 模式）
3. `check_install.py` 支持的 IDE 通过 profile 自动派生，不用动
4. 跑一份 smoke，把 transcript 拷进 `fixtures/transcripts/<newide>/`
5. `tests/test_parser_regression.py` 里 `IDE_DIALECT` 加一条

### 4.4 重装 pre-commit hook

```sh
./scripts/install-hooks.sh
```

场景：`git clone` 后第一次 / `.git/hooks/pre-commit` 被误删。

### 4.5 敏感扫描命中怎么办

`scripts/scan_sensitive.py` 抓到东西时：

1. **确认是不是真泄漏**：如果是 example 字符串 / doc 里的假 key，加到 `ALLOWED_LITERALS` 白名单
2. **真泄漏**：立刻 rotate 那个 key（Anthropic Console / OpenAI 平台 / GitHub PAT 页面），**不要**只是删文件——已经在 git history 里了
3. rotate 完更新代码，正常提交

---

## 5. 自动触发结构

Trtc-Eval 目前有 3 种触发源：

| 触发 | 干什么 | 需要 |
|---|---|---|
| PR / push to main | P1 + parser regression + secret scan（如果 PR 里有 eval-runs 变更，还跑 P2 打分） | 无 |
| **每天 03:07 UTC cron** | 只跑 P1，追踪 npm `@latest` 变化 | 无 |
| **agent-skills 发版后 dispatch** | agent-skills release workflow 调用 `gh workflow run`，跑 P1 | agent-skills 侧一次性接线（见下） |

### 5.1 agent-skills 侧的接线（一次性）

在 agent-skills 仓 `.github/workflows/release.yml`（或类似发布 workflow）里加一步：

```yaml
- name: Trigger Trtc-Eval P1 install check
  # Fire-and-forget: don't block the release if the eval CI is down.
  continue-on-error: true
  env:
    GH_TOKEN: ${{ secrets.TRTC_EVAL_DISPATCH_PAT }}
  run: |
    gh workflow run "Skill Install Check (P1)" \
      --repo syozz-dot/Trtc-Eval \
      --ref main \
      -f npx_target="@tencent-rtc/trtc-agent-skills@${{ github.event.release.tag_name }}" \
      -f triggered_by="agent-skills release ${{ github.event.release.tag_name }}"
```

**Secrets 准备**（agent-skills 仓 → Settings → Secrets → Actions）：

- `TRTC_EVAL_DISPATCH_PAT`：一个 fine-grained PAT，只授 `Trtc-Eval` 仓的 **Actions: write**，别的都不给。60 天 rotate 一次。

**保持解耦**：这套接线里 agent-skills 仓只知道两件事：
- workflow 名字：`"Skill Install Check (P1)"`
- 输入参数：`npx_target` / `triggered_by`

Trtc-Eval 内部随便怎么改判定规则、加 case、改 workflow，只要这两个字符串不变，agent-skills 那边完全不用动。

### 5.2 debug：cron 没触发

看：https://github.com/syozz-dot/Trtc-Eval/actions/workflows/skill-check-install.yml — 应该每天有一次 `event: schedule` 的 run。

不见了的话：
- 仓库 60 天没活动，GitHub 会自动禁用 schedule。push 一次即可
- workflow 语法错误 → actionlint 检查

### 5.3 debug：release dispatch 没触发

- agent-skills 仓 → Actions → 看那个 release workflow 的日志，找 "Trigger Trtc-Eval P1 install check" step
- 401 / 403 → PAT 过期或权限不足
- 404 → workflow 名字对不上（重命名 workflow 时容易漏）

---

## 附录 A · Phase 3 白盒 trace 评测

**目的**：在 P2 外部行为观察（"AI 说了什么、走了哪个 skill"）之外，加一层"AI 内部真正做了什么"的断言 —— 检查 `~/.cache/trtc-traces/<sid>.jsonl` 里的事件流是否符合期望。

### A.1 什么时候用

- **P2 pass 但可能有 silent failure**：外部路由对了、内容也回了，但 hook 悄悄 fail_open、AI 读错了 slice 之类的看不见问题
- **验证 hooks 生效**：`hook_decision` 事件必须出现，没出现说明 hooks 层根本没跑
- **验证 AI 真读了某文件**（而非从训练数据编造）：`tool_call.Read.file_path` 断言

### A.2 隔离设计（跟用户端完全无关）

Phase 3 相关代码**只在 Trtc-Eval 仓**，agent-skills 一点不动。用户 `npx add @latest` 装的 skill 完全没有 PostToolUse hook。

- `phase3/tracer.py` — emit_trace 工具
- `phase3/trace_posttooluse.py` — PostToolUse hook 脚本
- `phase3/eval_runner.py` — inject / restore / archive 三合一

跑 eval 时：
1. `run_eval.py --with-trace` 把 hook 临时注入 `<working_dir>/.claude/settings.json`
2. Claude Code CLI 每次调 Read/Write/Edit/Bash 就触发 hook，写 trace jsonl
3. eval 结束 atexit 自动还原 settings.json（**原样恢复用户已有的 hook 配置**，不多不少）
4. 归档 `<out_dir>/traces/<sid>.jsonl`，可离线复判

### A.3 5 类可断言的事件（观测契约来自 skill）

| 事件 | 触发时机 | 生产可见 | eval 可见 |
|---|---|---|---|
| `session.write` | skill 更新 `.trtc-session.yaml` | ✅ | ✅ |
| `flow.enter` | flow.py 进入新阶段 | ✅ | ✅ |
| `state_machine.init` / `.advance` | 状态机初始化 / 转移 | ✅ | ✅ |
| `hook_decision` | Pre-hook 决策 allow / block / **fail_open** | ✅ | ✅ |
| `tool_call` | AI 用 Read/Write/Edit/Bash | ❌ 用户端不装 hook | ✅ 需 `--with-trace` |

**Cursor 盲区**：Cursor 不产生 PostToolUse 事件，`tool_call` 断言对 cursor 不可用（`ide_profiles.cursor.capabilities` 不含 `trace`，run_eval 自动跳过 trace_assertions）。cursor 上剩下 4 类事件仍可断言。

### A.4 case 里怎么写断言

在 `case.turns[i].expect.trace_assertions` 加数组，每条断言：

```json
{
  "event": "tool_call",
  "where": {"tool_name": "Read", "file_path": "trtc-docs"},
  "min_count": 1,
  "_note": "AI must physically read the trtc-docs skill file"
}
```

- **`where`**：AND 匹配。字符串值走**子串匹配**（`file_path` 里包含 `trtc-docs` 即可），其他值走等值匹配。
- **`min_count`** / **`max_count`**：默认 min=1、max 无限
- **`must_not: true`**：等价于 `min_count=0, max_count=0`，事件**必须不出现**

### A.5 跑法

```sh
# 单条 case 加 trace
python3 run_eval.py --ide claude-code --case P2-DOCS-ERRCODE --with-trace

# 全量 P2 + trace
python3 run_eval.py --ide claude-code --with-trace

# 输出：eval-runs/<date>/traces/<sid>.jsonl 保留下来，可离线复判
python3 score.py eval-runs/<date>/results.claude-code.yaml
```

### A.6 冒烟 case 现状

| Case | trace 断言 |
|---|---|
| `P2-DOCS-ERRCODE` | ① PostToolUse 至少 1 次触发 ② 无 fail_open |
| `P2-CHAT-PATH-B` | ① Read trtc-chat/**  ② session.write ≥ 1 |

### A.7 已知盲区

从 handoff 继承：

- **Bash exit≠0 时 PostToolUse 不触发**：失败命令在 `tool_call` trace 里完全不可见
- **`~/.cache/trtc-traces/` 里的 stale 事件**：run_eval 用"过去 10 分钟"cutoff 过滤，但真跑多条 case 时，前 case 的 trace 仍可能被后 case 判定看到。目前假设 case 间清 session（`clear_sessions()` 每 case 前自动跑），所以 sid 不同 → 不影响 —— 但如果多 case 都用 fallback sid（cli 会话 id）会串号，未来场景要留意。
- **onboarding 阶段 session_id 为 fallback**：hook 找不到 `.trtc-session.yaml` 时用 CLI 对话 id，判定不区分 —— 后续可以加 `session_id_source` 筛选

---

## 6. 术语与快速参考

### 观察点分类

| Tier | 观察点 | fail 行为 |
|---|---|---|
| critical ★ | `route_triggered` | fail 时短路整个 case，不看其他 |
| major | `reporting_called` / `hooks_guarded` / `session_state` / `clarification_raised` / `tools_called` | 任一 N → case fail |
| soft · | `route_level1` / `route_level2` | N 时记 "minor concern"，不 flip fail |

### 命令速查

| 用途 | 命令 |
|---|---|
| P1 全量 | `python3 check_install.py --ide all` |
| P2 单条自检 | `python3 run_eval.py --case P2-DOCS-ERRCODE` |
| P2 smoke | `python3 run_eval.py --ide <ide> --tags smoke` |
| P2 全量 | `python3 run_eval.py --ide <ide>` |
| 免费额度自检 | `python3 run_eval.py --ide <ide> --probe` |
| 打分（CLI） | `python3 score.py <results.yaml>` |
| 打分（markdown，CI 用） | `python3 score.py <results.yaml> --format markdown` |
| baseline 对比 | `python3 score.py <results.yaml> --baseline <prev-summary.json>` |
| fixture 回归 | `python3 tests/test_parser_regression.py` |
| 敏感扫描 | `python3 scripts/scan_sensitive.py` |
| pre-commit 装 | `./scripts/install-hooks.sh` |
| 手动触发 P1 CI | `gh workflow run "Skill Install Check (P1)" --repo syozz-dot/Trtc-Eval` |

### 关键文件

| 路径 | 用途 |
|---|---|
| `cases.json` | case 单一数据源；改了不用动脚本 |
| `check_install.py` | P1 |
| `run_eval.py` | P2 全自动跑 + parser + 判定器（含 `--with-trace` 入口） |
| `score.py` | 打分 + baseline diff |
| `phase3/` | Phase 3 白盒 trace（tracer + PostToolUse hook + eval_runner），eval-only |
| `fixtures/transcripts/<ide>/` | parser regression 的 golden 样本 |
| `tests/test_parser_regression.py` | 8 fixture 回归 |
| `scripts/scan_sensitive.py` | 敏感串扫描 |
| `scripts/install-hooks.sh` | 一键装 pre-commit |
| `.github/workflows/skill-check-install.yml` | P1 CI（PR + push + cron + workflow_dispatch） |
| `.github/workflows/parser-regression.yml` | fixture 回归 + 敏感扫描 CI |
| `.github/workflows/skill-eval-p2-score.yml` | 只在 PR 里 eval-runs 变更时跑，无 key 打分 |
| `.github/workflows/skill-ci-probe.yml` | 手动触发的 CLI 认证探测（研究性质） |

### 相关链接

- 仓库：https://github.com/syozz-dot/Trtc-Eval
- CI 概览：https://github.com/syozz-dot/Trtc-Eval/actions
- 方案背景（PM 视角规划文档）：`~/Desktop/trtc-eval-flow.html`
- 上游 skill：https://github.com/Tencent-RTC/agent-skills
