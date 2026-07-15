# TRTC Skill + Eval Monorepo

内部 monorepo，把 **TRTC agent skill 源代码** 和 **skill 评测系统** 放在同一个仓：

```
├── skill/          # TRTC agent skill 源代码（sync 到公开仓 Tencent-RTC/agent-skills）
│   ├── skills/           # SKILL.md × 7（trtc / trtc-onboarding / trtc-docs / ...）
│   ├── knowledge-base/   # 共享 knowledge base
│   ├── bin/              # installer CLI (node bin/cli.js add ...)
│   ├── hooks/, tools/    # skill 运行时组件
│   └── ...
│
├── eval/           # 内部专有评测系统（不 sync 出去）
│   ├── run_eval.py       # P2 全自动跑 + 判定器
│   ├── cases.json        # test case 单一数据源
│   ├── score.py          # 打分 + baseline diff
│   ├── coverage_report.py  bucket_classifier.py  # corpus 覆盖分析
│   ├── phase3/           # 白盒 trace 评测（--with-trace）
│   ├── fixtures/         # parser regression golden 样本
│   ├── eval-runs/        # 历次运行结果 + baseline
│   └── ...
│
└── .github/workflows/    # 混合 CI（skill install check + eval 打分 + corpus 覆盖）
```

## 上手

- **改 skill 源代码** → 看 [`skill/README.md`](./skill/README.md)
- **跑评测 / 加 case / 看报告** → 看 [`eval/README.md`](./eval/README.md) 和 [`eval/SOP.md`](./eval/SOP.md)

## Sync 到公开仓（agent-skills）

**只 `skill/` 目录会被 sync 到 upstream `Tencent-RTC/agent-skills`**。评测代码 (`eval/`) 是内部专有，不外泄。sync 工具（脚本 / 手工 rsync / subtree）只需要一条规则：**取 `skill/` 内容，忽略其他所有**。

## CI（5 份 workflow，全部零 API key）

| Workflow | 触发 | 干什么 |
|---|---|---|
| `skill-check-install.yml` | 每 PR · 每天 03:07 UTC | P1 装齐检查（4 IDE 并行）· 用本地 `skill/bin/cli.js` |
| `parser-regression.yml` | 每 PR | fixture 回归 + 敏感扫描 + Phase 3 wiring smoke |
| `skill-eval-p2-score.yml` | PR 里 `eval/eval-runs/**/results.*.yaml` 变更 | 打分 → 表格化报告贴 PR 评论 |
| `corpus-coverage-report.yml` | PR 里 `eval/eval-runs/**/transcripts/**.jsonl` 或 `results.*.yaml` 变更 | Corpus 覆盖报告贴 PR 评论 |
| `skill-ci-probe.yml` | 仅手动 | 探测 IDE CLI 认证方式（研究性质） |

CI 只做**确定性分析**（打分、bucket 分类、fixture 回归），LLM 步骤走开发者本地 Pro 订阅额度。详见 [`eval/SOP.md`](./eval/SOP.md#2-日常流程每-pr)。
