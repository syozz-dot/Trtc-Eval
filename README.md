# TRTC Skill Eval

TRTC agent-skills 多 IDE 评测工具集。回答两个问题：

1. **skill 装得对不对？** — Phase 1 全量资产分发检查
2. **skill 用得对不对？** — Phase 2 行为评测（8 个观察维度）

方案背景与决策见 [`trtc-eval-flow.html`](./trtc-eval-flow.html)。

---

## 快速开始

**前置条件**：
- 目标 IDE 装好 skill：`npx -y @tencent-rtc/trtc-agent-skills@latest add`
- 有对应 IDE 的 headless CLI（`claude` / `cursor-agent` / `codex` / `codebuddy`）
- Python 3.9+，`pip install pyyaml`

### Phase 1：查装齐没

```sh
# 4 IDE 全量资产检查
python3 check_install.py --ide all

# 只查某个 IDE
python3 check_install.py --ide claude-code
```

退出码 0 = 全绿，退出码 1 = 有资产缺失。可直接接 CI。

### Phase 2：全自动跑行为评测

```sh
# 跑全部 P2 case（10 条，约 15 分钟）
python3 run_eval.py --ide claude-code --out-dir ./eval-runs/v1

# 只跑单条快速自检
python3 run_eval.py --case P2-DOCS-ERRCODE

# 只跑 smoke tag（快，都是单轮 FAQ）
python3 run_eval.py --tags smoke

# 打分出报告
python3 score.py ./eval-runs/v1/results.claude-code.yaml
```

自动流程：读 `cases.json` → 调 `claude -p` 跑 prompt → 解析 JSONL 事件流 → 自动比对预期写 Y/N → `results.claude-code.yaml` → `score.py` 打分。

### Phase 2：--probe 免费额度自检

跑一条最简 prompt + 便宜模型（cursor `auto` / claude `haiku` / codebuddy `claude-haiku-4.5` / codex 默认），只验证 CLI 可达 + 事件流能被解析器正确处理。**不做任何观察点判定，不消耗真实评测额度**。适合：

- 新 IDE 首次集成后快速自检
- 某个 IDE 的 CLI 升级后确认事件流没变
- Cursor Pro 配额紧张时验证脚本仍能工作

```sh
python3 run_eval.py --ide cursor --probe
python3 run_eval.py --ide claude-code --probe --probe-model haiku
```

30 秒内完成，输出事件类型分布 + session_id 提取状态 + result 状态。

### Phase 2：人工模式（备用）

如果 IDE headless 通道不可用（如 Cursor 配额耗尽时），走人填模式：

```sh
python3 generate.py --ide claude-code   # 生成 testsheet.md + results_template.yaml
cp results_template.yaml results.claude-code.yaml
# 打开 testsheet.md，逐条在 IDE 里粘贴 prompt，肉眼观察 → yaml 里填 Y/N/S
python3 score.py results.claude-code.yaml
```

---

## 版本对比 / baseline

不需要专门跑一次。任意一次 `score.py` 都会写 `summary.<ide>.json`。下次跑时：

```sh
python3 score.py results.claude-code.yaml --baseline ./eval-runs/prev/summary.claude-code.json
```

报告里会多 `↑ / ↓ / →` 增量列。case 结构变了（如从单轮改多轮）会自动跳过增量计算，不当作回归。

---

## 评分规则

**pass 判定规则**：

1. **critical 短路**：`route_triggered`（trtc 主 skill 是否被激活）N → 整个 case 直接 fail，其他维度不用看
2. **hard 观察点全 Y** → pass；**任一 hard N** → fail
3. **soft 观察点** N 只记录 "minor concern"，**不拖 case 到 fail**（子 skill 二级路由暂时不作为回归依据）

**观察点分类**：

| 分类 | 观察点 | 拖 fail 吗 |
|---|---|---|
| **critical** ★ | `route_triggered` | 是（且短路） |
| **hard** | `reporting_called` / `hooks_guarded` / `session_state` / `clarification_raised` / `tools_called` | 是 |
| **soft** | `route_level1` / `route_level2` | **否**（记 minor concern） |

想调分类，改 `score.py:SOFT_OBS` 集合和 `OBS_TIER` 表即可。

**权重仅用于 score 数值展示**：critical=1.0 / major=1.0 / minor=0.5。不影响 pass/fail 判定。

**status 语义**：

| status | 语义 |
|---|---|
| `pass` | 全部 hard 观察点 Y（可能有 soft concern，但不影响状态） |
| `fail` | 至少一个 hard N（含 critical fail） |
| `incomplete` | 未填 (`?`) 比例 > 50% —— 一般是 yaml 没填完 |
| `skipped_capability` | case 声明了 IDE 缺失的能力（如 Codex 无 hook） |

**报告**：底部会分两栏——`FAIL 明细`（真正 fail 的 case + 观察点定位）和`待关注`（pass 但有 soft concern 的 case）。

---

## 支持的 IDE

| IDE | Phase 1 | Phase 2 全自动 | 备注 |
|---|---|---|---|
| **claude-code** | ✅ | ✅ | 已实测跑通 |
| **cursor** | ✅ | ✅ | 脚本支持；实机跑通 stream-json 事件解析（本机额度状态可能影响端到端） |
| **codebuddy** | ✅ | ✅ | 脚本支持（事件流与 claude 同构，共享 dialect） |
| **codex** | ✅ | ✅ | **已实测跑通**（3/3 pass on P2-DOCS-ERRCODE），Codex 事件流独立方言 (`thread.started` / `item.completed`) 已解析 |

跑其他 IDE：`python3 run_eval.py --ide <cursor|codebuddy|codex> --case P2-DOCS-ERRCODE`

---

## 两种运行方式

**A. 手动 CLI**：直接在终端跑
```sh
python3 run_eval.py --ide claude-code --tags smoke
```

**B. 让另一个 IDE 里的 AI 代跑**：在 Cursor / CodeBuddy 里对 AI 说：
> 帮我跑 `python3 run_eval.py --ide claude-code --tags smoke`，跑完对 results 调用 `python3 score.py` 打分，把 fail 明细贴给我

AI 用它自己的 Bash 工具跑命令，评测本身仍由 run_eval.py 完成。**评测器和被测器保持隔离**——用 Cursor 驱动可以评测 claude-code / codex / codebuddy，反之亦然。

⚠️ **不要**让被测 IDE 自己跑针对自己的评测（如让 claude-code 里的 AI 跑 `--ide claude-code`）——同一会话/上下文会互相干扰。

---

## 文件结构

```
trtc-eval/
├── cases.json               单一数据源（10 P2 + 4 P1，含 asset_catalog / ide_profiles）
├── check_install.py         Phase 1 检查器
├── generate.py              Phase 2 测试单生成器（人工模式）
├── run_eval.py              Phase 2 全自动评测器
├── score.py                 打分 + baseline 对比
├── testsheet.md             (自动生成) 人读题目单
├── results_template.yaml    (自动生成) 空白答题卡
├── trtc-eval-flow.html      方案规划文档（PM 视角）
└── AGENTS.md / CLAUDE.md / CODEBUDDY.md   (npx add 生成，AI 指令文件)
```

---

## 添加新用例

改 `cases.json` 就够了，脚本无需改动：

- **加/删 case** → 加到 `cases[]` 数组
- **加新观察维度** → 加到顶层 `obs_keys` 字典 + 在某条 case 的 `expect` 里引用
- **改 prompt / 期望** → 直接改 case 里的字段

`run_eval.py` 里若维度需要新的自动判定逻辑（当前支持 8 种维度），需要在 `evaluate_observation()` 里加分派——不加也不会崩，会自动标 `S`（无法判定）。

---

## 已知遗留

- Cursor 完整事件流实测（等 7/9 Pro 配额重置）
- run_eval.py 拓 codex / codebuddy / cursor（主逻辑不动，改配置切命令名）
- Phase 1 接入 GitHub CI
- Phase 3 LLM Judge（二期，仍走 CLI 形态）
