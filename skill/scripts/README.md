# scripts/ — Slice / Scenario 校验脚本

> 这些脚本是 [`knowledge-base/slice-spec.md`](../knowledge-base/slice-spec.md) 与
> [`knowledge-base/scenario-spec.md`](../knowledge-base/scenario-spec.md) 中
> 「必填项语义三件套」的「验证手段」实现。
>
> 没有这些脚本,spec 里的「不可合并 / 批量回退」等强制语言就是空头支票。

## 安装

```bash
pip install -r scripts/requirements.txt
```

依赖:
- `PyYAML`(frontmatter / index.yaml 解析)
- `requests`(`validate_api_docs.py` 在线模式;离线时不需要)

## 脚本一览

| 脚本 | 校验对象 | 退出码 | 对应 spec 章节 |
|---|---|---|---|
| `validate_frontmatter.py` | slice frontmatter 字段齐全 + 与 index.yaml 一致 | 0 通过 / 1 失败 / 2 用法错 | slice-spec.md 第四节 Frontmatter |
| `validate_api_docs.py` | 平台 slice 的 api_docs 链接精确到类级 | 0 / 1 / 2 | slice-spec.md 第四节 api_docs 字段 |
| `check_must_rules.py` | 「代码生成约束」MUST/MUST NOT 红旗词 + Verify 完整 | 0 / 1 / 2 | slice-spec.md 第四节 + MUST 维度对齐原则 |
| `check_verify_matrix.py` | 「验证矩阵」4 层各 ≥1 + 覆盖所有 MUST | 0 / 1 / 2 | slice-spec.md 第四节 验证矩阵 |
| `extract_code.py` | 抽取 markdown 代码块,供编译 / lint 验证 | 永远 0(工具脚本) | slice-spec.md 代码示例标准 |
| `validate_scenario.py` | scenario 章节齐全 + slice id 一致 + B-多选明文声明 | 0 / 1 / 2 | scenario-spec.md 第五节 字段一致性检查 |

## 通用约定

- 接受文件或目录;目录会递归找 `.md`
- 失败信息格式:`{file}:{line}: [{CODE}] {message}`,可被 `grep` 过滤
- 同一文件内**不会因第一个错误就 bail**,会列出所有问题让你一次修完
- 退出码:
  - `0` 全部通过
  - `1` 至少一个文件存在 error
  - `2` 用法错误(无参数等)

## 用法示例

### 单文件校验

```bash
python3 scripts/validate_frontmatter.py knowledge-base/slices/live/coguest-apply.md
python3 scripts/check_must_rules.py knowledge-base/slices/live/ios/coguest-apply.md
```

### 整个目录(slice / scenario)

```bash
# 所有 slice
python3 scripts/validate_frontmatter.py knowledge-base/slices/

# 所有 scenario
python3 scripts/validate_scenario.py knowledge-base/scenarios/

# 仅 ios 平台
python3 scripts/check_must_rules.py knowledge-base/slices/live/ios/
```

### `validate_api_docs.py` 离线 / 在线

默认在线:每个 url 请求 200 + 检查页面 H1 包含 frontmatter title。

```bash
# CI 中没网?用离线模式只做静态格式校验
python3 scripts/validate_api_docs.py --offline knowledge-base/slices/live/ios/

# 自定义超时(默认 10 秒)
python3 scripts/validate_api_docs.py --timeout=20 path/to/slice.md

# 跳过 H1 检查(SPA 站点)
python3 scripts/validate_api_docs.py --no-h1-check path/to/slice.md
```

### `validate_scenario.py` 严格模式

由于现存 scenario 文件多数是历史结构,默认行为是:
- **error** = 与 index.yaml 不一致这类硬性事实错误
- **warning** = 章节缺失 / 用词软等结构性问题(老文件常见)

加 `--strict` 时,所有 warning 升级为 error:

```bash
# 老文件兼容(只挂硬错误)
python3 scripts/validate_scenario.py knowledge-base/scenarios/

# 新文件 / 重写后的文件(全部按 spec 卡死)
python3 scripts/validate_scenario.py --strict knowledge-base/scenarios/conference/base/
```

### `extract_code.py` 用法

工具脚本,不参与通过/失败判定:

```bash
# 全部代码 → stdout
python3 scripts/extract_code.py knowledge-base/slices/live/ios/coguest-apply.md

# 仅 swift,管道给编译器
python3 scripts/extract_code.py --lang=swift path/to/slice.md > /tmp/check.swift

# 列代码块元信息
python3 scripts/extract_code.py --list path/to/slice.md

# 按语言拆分到目录
python3 scripts/extract_code.py --by-lang=/tmp/extracted/ path/to/slice.md
```

## 在 PR 中使用

DoD 清单(slice-spec.md 第五节)要求每个验证项 **粘贴命令输出到 PR 描述**。建议:

```bash
# 一次性跑全套(slice 平台实现文件示例)
F=knowledge-base/slices/live/ios/coguest-apply.md
python3 scripts/validate_frontmatter.py $F
python3 scripts/validate_api_docs.py --offline $F
python3 scripts/check_must_rules.py $F
python3 scripts/check_verify_matrix.py $F
```

退出码全部为 0 → 把命令输出贴到 PR description 即可证明你跑过了。

## 在 CI 中接入

最小 GitHub Actions(示意):

```yaml
- name: Validate slice/scenario specs
  run: |
    pip install -r scripts/requirements.txt
    python3 scripts/validate_frontmatter.py knowledge-base/slices/
    python3 scripts/validate_api_docs.py --offline knowledge-base/slices/
    python3 scripts/check_must_rules.py knowledge-base/slices/
    python3 scripts/check_verify_matrix.py knowledge-base/slices/
    python3 scripts/validate_scenario.py knowledge-base/scenarios/
```

## 现阶段已知限制

1. **`check_must_rules.py` 的红旗词检测**只在规则文字层面做字符串匹配,不区分语义。
   极少数情况下"或"出现在 backtick 内描述中是合法的(如错误码字符串),目前会误报——
   遇到时拆成多条原子规则即可。
2. **`validate_api_docs.py` 在线模式**对动态 SPA 站点的 H1 检查会误报,加 `--no-h1-check`。
3. **`validate_scenario.py` 默认对老文件友好**(发 warning),新建/重写的 scenario 文件
   建议加 `--strict`。
4. 脚本目前**未实现** `--fix` 自动修复 —— 只报告问题,人来改。

## 错误码字典

| 前缀 | 含义 |
|---|---|
| `FM-*` | frontmatter 字段问题 |
| `API-DOCS-*` | api_docs 字段问题 |
| `MUST-*` | MUST 规则问题 |
| `MATRIX-*` | 验证矩阵问题 |
| `SEC-*` | 章节缺失 |
| `SLICE-*` | scenario 中 slice id 一致性 |
| `FORM-B-*` | scenario B 形态结构 |
| `BMULTI-*` | scenario B-多选 over-integration 防护 |
| `CHECKLIST-*` | 验收 Checklist 软词 |
