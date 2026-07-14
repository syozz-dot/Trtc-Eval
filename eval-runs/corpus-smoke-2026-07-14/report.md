# TRTC Skill · Corpus 评测覆盖报告

**IDE**: claude-code  ·  **日期**: 2026-07-14  ·  **out-dir**: `corpus-smoke-2026-07-14`

**范围**: 2 / 8 条 corpus seed 已跑 · 触发正确性覆盖 2 · bucket 覆盖 2

本报告聚合两个 orthogonal 信号：
1. **触发正确性**（skill/工具按预期触发）— 通过 8 维度 Y/N 判定
2. **能力覆盖**（回答有没有实质内容 + 数据源）— 通过 bucket A/B/C/D/E? 判定

触发正确性 pass 但 bucket ∈ {B/C/D/E?} 是**核心缺口信号** —— 路由/工具都对，但能力有暗雷。

---

## 1. 触发正确性

**Pass rate**: 2/2 = 100.0%

| Case | Product | Intent | Pass | Fail / Concern |
|---|---|---|---|---|
| P2-CORPUS-CHAT-001 | Chat | capability_lookup | ✅ | - |
| P2-CORPUS-LIVE-001 | Live | api_lookup | ✅ | - |

> `route_level1/2` 是 soft observation：N 只记 minor concern，不拖 case 到 fail。其他 hard 观察点任一 N 都会拖 fail。

---

## 2. 能力覆盖 · Bucket 分布

| Case | Product | Bucket | Path (数据源) | Tools | Errors | 说明 |
|---|---|:---:|---|---:|---:|---|
| P2-CORPUS-CHAT-001 | Chat | **A** | 4 slice + webfetch | 33 | 8 | answered from 4 local slice(s) |
| P2-CORPUS-LIVE-001 | Live | **B** | docsbot | 9 | 1 | docsbot resolved but no local slice — local KB coverage gap |

### 按产品聚合

| Product | Cases | A | B | C | D | E? | 结论 |
|---|---:|---:|---:|---:|---:|---:|---|
| Chat | 1 | 1 | 0 | 0 | 0 | 0 | 本地 KB 完整覆盖 |
| Live | 1 | 0 | 1 | 0 | 0 | 0 | ⚠️ 全部依赖 docsbot（本地 KB 缺） |

### 高频缺口 top-N (B/C/D/E?)

- **P2-CORPUS-LIVE-001** [Live] bucket=**B**: docsbot resolved but no local slice — local KB coverage gap  
  · path=`docsbot` · tools=9 · errors=1

---

## 3. Token / Tool 消耗速览

| Case | Product | Bucket | Tools | Errors | Slices | WebFetch | 备注 |
|---|---|:---:|---:|---:|---:|:---:|---|
| P2-CORPUS-CHAT-001 | Chat | A | 33 | 8 | 4 | ✓ | ⚠️ 高 error 计数 → 可能触发 fallback 循环 |
| P2-CORPUS-LIVE-001 | Live | B | 9 | 1 | 0 | ✗ |  |

> 关注 tools 数量、error 数量、slice 读取数——这三个指标与 token 消耗强相关。
> Chat Path D 的高 token 消耗典型特征：多 slice + webfetch fallback + 多 tool_error。

---

## 4. 结论与后续

**判定信号总结**：
- 触发正确性 pass rate: 2/2
- Bucket 分布: A=1, B=1, C=0, D=0, E?=0

**已知限制**：
- 本次仅覆盖 2/8 条 corpus seed，样本量小
- xlsx 全量 2078 条 corpus 待接入（Task #5 · dump_corpus.py）
- Bucket E?（疑似幻觉）需 LLM judge 二次确认，本工具不做
