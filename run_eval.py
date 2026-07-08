#!/usr/bin/env python3
"""
run_eval.py — Phase 2 全自动评测器 POC (claude-code)

对每条 P2 case 逐轮跑 claude -p，从 stream-json transcript 里解析工具调用，
按 expected_behavior 自动判 Y/N，产出 results.<ide>.yaml + 每 case 转录留档。

Usage:
    # 真跑（消耗 claude 额度）
    python3 run_eval.py --ide claude-code --out-dir ./eval-runs/v1

    # 只跑一条 case 试水
    python3 run_eval.py --ide claude-code --case P2-DOCS-ERRCODE

    # 只跑打了 smoke tag 的 case
    python3 run_eval.py --ide claude-code --tags smoke

    # dry-run：不调 claude，用假 transcript 走一遍解析器（自测用）
    python3 run_eval.py --ide claude-code --dry-run

Output:
    <out-dir>/results.<ide>.yaml               答题卡（可直接喂 score.py）
    <out-dir>/transcripts/<case_id>.turn<N>.jsonl  每轮真实转录留档
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


# ── stream-json 事件解析器 ─────────────────────────────────────────────────

@dataclass
class ToolCall:
    name: str          # "Bash" / "Skill" / "Read" / ...
    input: dict        # {"command": "...", ...}
    id: str            # tool_use_id


@dataclass
class ToolResult:
    tool_use_id: str
    content: str
    is_error: bool = False


@dataclass
class ParsedTranscript:
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: dict[str, ToolResult] = field(default_factory=dict)
    text_blocks: list[str] = field(default_factory=list)
    result_status: str = ""    # from final result event ("" = 未设置; success / error_* / failed)
    error: str | None = None

    @property
    def bash_commands(self) -> list[str]:
        """所有 Bash tool_use 的 command 字符串。"""
        return [
            tc.input.get("command", "")
            for tc in self.tool_calls
            if tc.name == "Bash"
        ]

    @property
    def skill_activations(self) -> list[str]:
        """所有 Skill tool_use 激活的 skill 名。"""
        return [
            tc.input.get("skill", "")
            for tc in self.tool_calls
            if tc.name == "Skill"
        ]

    @property
    def all_text(self) -> str:
        return "\n".join(self.text_blocks)


def parse_transcript(jsonl_text: str, dialect: str = "claude") -> ParsedTranscript:
    """
    把 headless CLI 的 stream-json 输出解析成结构化事件。

    dialect="claude": 适用于 claude-code / cursor / codebuddy
        事件家族: system.init / user / assistant.tool_use / user.tool_result / result
    dialect="codex": 适用于 OpenAI codex CLI
        事件家族: thread.started / turn.started / item.completed(command_execution|tool_call|agent_message) / turn.completed
    """
    result = ParsedTranscript()

    if dialect == "codex":
        return _parse_codex(jsonl_text, result)

    # 默认 claude 方言
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = e.get("type")

        if etype == "assistant":
            for block in e.get("message", {}).get("content", []):
                btype = block.get("type")
                if btype == "tool_use":
                    result.tool_calls.append(ToolCall(
                        name=block.get("name", ""),
                        input=block.get("input", {}),
                        id=block.get("id", ""),
                    ))
                elif btype == "text":
                    result.text_blocks.append(block.get("text", ""))
                # thinking blocks 忽略

        elif etype == "user":
            for block in e.get("message", {}).get("content", []):
                if block.get("type") == "tool_result":
                    tid = block.get("tool_use_id", "")
                    content = block.get("content", "")
                    if isinstance(content, list):
                        content = "\n".join(
                            c.get("text", "") if isinstance(c, dict) else str(c)
                            for c in content
                        )
                    result.tool_results[tid] = ToolResult(
                        tool_use_id=tid,
                        content=str(content),
                        is_error=block.get("is_error", False),
                    )

        elif etype == "result":
            result.result_status = e.get("subtype", "ok")
            if "error" in e:
                result.error = e["error"]

    return result


def _parse_codex(jsonl_text: str, result: ParsedTranscript) -> ParsedTranscript:
    """Codex CLI 事件流解析器。

    codex 的 tool 调用是 item.completed 里 item.item_type == 'command_execution' 或 'tool_call'。
    - command_execution: 相当于 Bash tool_use，字段 command / stdout / exit_code
    - tool_call:         相当于其他 tool_use（Skill / Read / Grep 等），字段 name / arguments
    - agent_message:     相当于 assistant.text
    """
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue  # 跳过 codex 输出顶部的 stderr 提示行 "Reading additional input..."
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = e.get("type", "")

        if etype == "item.completed":
            item = e.get("item", {})
            it = item.get("item_type", item.get("type", ""))

            if it == "command_execution":
                cmd = item.get("command", "")
                # 把 codex 的 command 映射成 claude 方言的 Bash tool_use
                cid = item.get("id", "")
                result.tool_calls.append(ToolCall(
                    name="Bash",
                    input={"command": cmd},
                    id=cid,
                ))
                # 输出映射为 tool_result
                stdout = item.get("stdout", "") or ""
                stderr = item.get("stderr", "") or ""
                exit_code = item.get("exit_code", 0)
                result.tool_results[cid] = ToolResult(
                    tool_use_id=cid,
                    content=(stdout + ("\n[stderr]\n" + stderr if stderr else "")),
                    is_error=exit_code != 0,
                )

            elif it == "tool_call":
                name = item.get("name", "")
                # codex 的 arguments 通常是 JSON 字符串
                args = item.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}
                cid = item.get("id", "")
                result.tool_calls.append(ToolCall(
                    name=name,
                    input=args if isinstance(args, dict) else {},
                    id=cid,
                ))
                # tool_call 的输出可能在 item.output / item.result
                output = item.get("output") or item.get("result") or ""
                if isinstance(output, dict):
                    output = json.dumps(output, ensure_ascii=False)
                result.tool_results[cid] = ToolResult(
                    tool_use_id=cid,
                    content=str(output),
                    is_error=False,
                )

            elif it == "agent_message":
                text = item.get("text", "")
                if text:
                    result.text_blocks.append(text)

        elif etype == "turn.failed":
            result.result_status = "failed"
            result.error = json.dumps(e.get("error") or e, ensure_ascii=False)

        elif etype == "turn.completed":
            if not result.result_status:
                result.result_status = "success"

    return result


# ── 观察点判定器 ──────────────────────────────────────────────────────────

def _match_reporting_call(bash_cmds: list[str], required_scripts: list[str]) -> tuple[bool, str]:
    """
    检查 bash 命令里是否都出现了 required_scripts 声明的脚本调用。
    每个 required 元素形如 'reporting.py prompt' 或 'reporting.py context'。
    """
    missing = []
    for req in required_scripts:
        # req 形如 "reporting.py prompt" — 以 "reporting.py" 出现且后接 "prompt" 判定
        parts = req.split()
        script = parts[0]
        subcmd = parts[1] if len(parts) > 1 else None

        found = False
        for cmd in bash_cmds:
            if script in cmd and (not subcmd or subcmd in cmd):
                found = True
                break
        if not found:
            missing.append(req)

    if missing:
        return False, f"missing: {', '.join(missing)}"
    return True, f"all {len(required_scripts)} script(s) called"


def _match_route_level1(transcript: ParsedTranscript, target: str, must_not: list[str]) -> tuple[bool, str]:
    """
    一级路由判断。看三处证据：
    1. Skill tool_use 的 skill 参数
    2. Bash 命令里出现的 skill 目录路径（如 skills/trtc-docs/）
    3. Read 工具的 file_path 里出现的 skill 目录（读 SKILL.md 也算路由证据）
    """
    activations = [s for s in transcript.skill_activations if s]

    # 从各种 tool 参数里提取 skills/<name>/ 引用
    skill_paths = set()
    pattern = re.compile(r"skills/(trtc(?:-[a-z-]+)?)/")

    for tc in transcript.tool_calls:
        if tc.name == "Bash":
            cmd = tc.input.get("command", "")
            skill_paths.update(pattern.findall(cmd))
        elif tc.name in ("Read", "Grep", "Glob", "Edit", "Write"):
            for field in ("file_path", "path", "pattern"):
                v = tc.input.get(field, "")
                if isinstance(v, str):
                    skill_paths.update(pattern.findall(v))

    all_targets = set(activations) | skill_paths
    hit_target = target in all_targets
    hit_bad = [x for x in must_not if x in all_targets]

    if hit_target and not hit_bad:
        return True, f"routed to {target} (evidence: {sorted(all_targets)})"
    if not hit_target:
        return False, f"expected {target}, got {sorted(all_targets) or '<none>'}"
    if hit_bad:
        return False, f"routed correctly but also hit forbidden: {hit_bad}"
    return False, "unknown"


def _match_route_triggered(transcript: ParsedTranscript, expected_skill: str) -> tuple[bool, str]:
    """trtc 主 skill 是否被激活。"""
    if expected_skill in transcript.skill_activations:
        return True, f"Skill activated: {expected_skill}"
    # 兜底：任何指向 skills/trtc/ 的 Bash 也算激活
    for cmd in transcript.bash_commands:
        if f"skills/{expected_skill}/" in cmd or f"skills/{expected_skill}\"" in cmd:
            return True, f"skills/{expected_skill}/ referenced in Bash"
    return False, f"no Skill or Bash reference to {expected_skill}"


def _match_clarification(transcript: ParsedTranscript, topics: list[str]) -> tuple[bool, str]:
    """
    追问判定（弱信号）。看两处：
    1. AskUserQuestion tool_use（原生追问工具）
    2. text 里出现追问关键词（"web 还是 iOS"、"Which platform"、"哪个平台" 等）
    """
    for tc in transcript.tool_calls:
        if tc.name == "AskUserQuestion":
            return True, "AskUserQuestion tool used"

    text = transcript.all_text.lower()
    for topic in topics:
        # 简单启发式：文本里同时出现 topic 关键词 + 疑问句形式
        if topic == "platform":
            if any(w in text for w in ["web", "ios", "android", "平台", "platform"]) and \
               any(q in text for q in ["?", "？", "哪个", "which", "which one"]):
                return True, "asked about platform (heuristic)"
        elif topic == "product":
            if any(q in text for q in ["?", "？", "哪种", "which"]):
                return True, "asked about product (heuristic)"

    return False, f"no clarification for topics: {topics}"


def _match_tools_called(transcript: ParsedTranscript, expect: dict) -> tuple[bool, str]:
    """
    tools_called: 检查 required / any_of 中的工具是否被调用。
    工具名匹配 Bash 命令里是否包含 'tools.<name>' 或 'tools/<name>.py'。
    """
    def _tool_used(tool_name: str) -> bool:
        for cmd in transcript.bash_commands:
            if f"tools.{tool_name}" in cmd or f"tools/{tool_name}.py" in cmd:
                return True
        return False

    required = expect.get("required", [])
    any_of = expect.get("any_of", [])
    must_not = expect.get("must_not", [])

    problems = []
    for r in required:
        if not _tool_used(r):
            problems.append(f"missing required tool: {r}")

    if any_of:
        if not any(_tool_used(t) for t in any_of):
            problems.append(f"none of any_of={any_of} called")

    for m in must_not:
        if _tool_used(m):
            problems.append(f"forbidden tool called: {m}")

    if problems:
        return False, "; ".join(problems)
    return True, "all tool constraints satisfied"


def _match_hooks_guarded(transcript: ParsedTranscript, expect: dict) -> tuple[bool, str]:
    """
    hooks_guarded: 检查 hook 是否被正确触发拦截。
    在 stream-json 里，hook 拦截通常表现为 tool_result 有 is_error=true 或
    content 里含 "hook blocked" / "gate_slice_write.py" 等字样。
    """
    hook_name = expect.get("hook", "")
    should_block = expect.get("should_block", False)

    hook_signals = 0
    for tr in transcript.tool_results.values():
        if tr.is_error and hook_name in tr.content:
            hook_signals += 1
        elif hook_name and hook_name in tr.content:
            hook_signals += 1

    if should_block:
        if hook_signals > 0:
            return True, f"hook {hook_name} blocked (signals={hook_signals})"
        return False, f"hook {hook_name} did not block"
    else:
        if hook_signals == 0:
            return True, f"hook {hook_name} correctly did not fire"
        return False, f"hook {hook_name} unexpectedly fired"


def _match_session_state(transcript: ParsedTranscript, expect: dict, working_dir: Path) -> tuple[bool, str]:
    """
    session_state: 读 .trtc-session.yaml 检查 status/product/platform，
    或检查其他布尔期望（no_direct_code_gen、resumed_from_guard 等）。
    session 文件在 skills/trtc/ 目录里（skill 内部维护），不在 working_dir 根。
    """
    # 布尔期望
    if expect.get("no_direct_code_gen"):
        # 检查是否有 Write / Edit tool_use（生成代码的信号）
        code_written = any(tc.name in ("Write", "Edit") for tc in transcript.tool_calls)
        if not code_written:
            return True, "no direct code generation observed"
        return False, "code was written despite no_direct_code_gen expectation"

    if expect.get("resumed_from_guard"):
        # 弱信号：转录里出现 "session guard" 或跳过分类的证据
        text = transcript.all_text.lower()
        if any(x in text for x in ["session guard", "resume", "恢复"]):
            return True, "session resumed (heuristic)"
        return False, "no evidence of session resume"

    # session 文件字段检查 —— 找 skills/*/  下最新的 .trtc-session.yaml
    candidates = [
        working_dir / ".claude" / "skills" / "trtc" / ".trtc-session.yaml",
        working_dir / ".cursor" / "skills" / "trtc" / ".trtc-session.yaml",
        working_dir / ".codebuddy" / "skills" / "trtc" / ".trtc-session.yaml",
        working_dir / ".codex" / "skills" / "trtc" / ".trtc-session.yaml",
        working_dir / ".trtc-session.yaml",
    ]
    session_file = next((p for p in candidates if p.exists()), None)
    if not session_file:
        return False, f".trtc-session.yaml not found in any skills/trtc/ subdir under {working_dir}"

    try:
        import yaml
        with open(session_file) as f:
            sess = yaml.safe_load(f) or {}
    except Exception as e:
        return False, f"cannot read session file: {e}"

    problems = []
    for key in ("status", "product", "platform"):
        if key in expect:
            actual = sess.get(key)
            if actual != expect[key]:
                problems.append(f"{key}: expected {expect[key]!r}, got {actual!r}")

    if problems:
        return False, "; ".join(problems)
    return True, f"session state matches ({session_file.name})"


# ── 判定分派 ────────────────────────────────────────────────────────────────

def evaluate_observation(
    obs_key: str,
    detail,
    transcript: ParsedTranscript,
    working_dir: Path,
) -> tuple[str, str]:
    """
    对一个 (obs_key, expected_detail) 做自动判定。
    返回 (verdict, reason) — verdict 是 "Y" / "N" / "S"（S = 无法判定）。
    """
    if not isinstance(detail, dict):
        return ("S", f"non-dict expect: {detail!r}")

    try:
        if obs_key == "route_triggered":
            skill = detail.get("skill", "trtc")
            ok, reason = _match_route_triggered(transcript, skill)
            return ("Y" if ok else "N", reason)

        if obs_key == "route_level1":
            if detail.get("deferred"):
                # 期望"应该推迟路由"：检查除 trtc 外没有其他 skill 激活
                other = [s for s in transcript.skill_activations if s != "trtc"]
                if not other:
                    return ("Y", "no premature routing to domain skill")
                return ("N", f"prematurely routed to: {other}")
            target = detail.get("target", "")
            must_not = detail.get("must_not", [])
            ok, reason = _match_route_level1(transcript, target, must_not)
            return ("Y" if ok else "N", reason)

        if obs_key == "route_level2":
            # 二级路由：转录里是否出现目标 path 的关键词/文件路径
            target = detail.get("target", "")
            text = transcript.all_text.lower()
            if target.lower() in text:
                return ("Y", f"level2 target {target} referenced in output")
            # 弱信号，多半需要人工
            return ("S", f"cannot verify level2 target {target} automatically")

        if obs_key == "reporting_called":
            scripts = detail.get("scripts", [])
            ok, reason = _match_reporting_call(transcript.bash_commands, scripts)
            return ("Y" if ok else "N", reason)

        if obs_key == "clarification_raised":
            topics = detail.get("topics", [])
            ok, reason = _match_clarification(transcript, topics)
            return ("Y" if ok else "N", reason)

        if obs_key == "tools_called":
            ok, reason = _match_tools_called(transcript, detail)
            return ("Y" if ok else "N", reason)

        if obs_key == "hooks_guarded":
            ok, reason = _match_hooks_guarded(transcript, detail)
            return ("Y" if ok else "N", reason)

        if obs_key == "session_state":
            ok, reason = _match_session_state(transcript, detail, working_dir)
            return ("Y" if ok else "N", reason)

        return ("S", f"no matcher for obs_key={obs_key}")

    except Exception as e:
        return ("S", f"matcher error: {e}")


# ── session 清理 ────────────────────────────────────────────────────────────

SESSION_FILE_GLOBS = [
    ".claude/skills/trtc/.trtc-session.yaml",
    ".claude/skills/trtc/.trtc-session.yaml.lock",
    ".cursor/skills/trtc/.trtc-session.yaml",
    ".cursor/skills/trtc/.trtc-session.yaml.lock",
    ".codebuddy/skills/trtc/.trtc-session.yaml",
    ".codebuddy/skills/trtc/.trtc-session.yaml.lock",
    ".codex/skills/trtc/.trtc-session.yaml",
    ".codex/skills/trtc/.trtc-session.yaml.lock",
    ".trtc-session.yaml",
    ".trtc-session.yaml.lock",
]


def clear_sessions(working_dir: Path) -> int:
    """删除所有 IDE 目录下的 .trtc-session.yaml，避免上条 case 状态污染下一条。"""
    n = 0
    for rel in SESSION_FILE_GLOBS:
        p = working_dir / rel
        if p.exists():
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
    return n




def find_cli_bin(profile: dict) -> str:
    """按 profile 定位 CLI 可执行文件；未找到则退出。"""
    binary = profile.get("cli", {}).get("binary")
    if not binary:
        sys.exit("[run_eval] profile.cli.binary missing")

    # 环境变量覆盖：{IDE_UPPER}_BIN，如 CLAUDE_BIN / CURSOR_AGENT_BIN
    env_key = binary.upper().replace("-", "_") + "_BIN"
    override = os.environ.get(env_key)
    if override and Path(override).exists():
        return override

    # 常见位置查找
    for cand in [
        binary,                                                 # PATH
        f"{os.path.expanduser('~')}/.local/bin/{binary}",
        f"{os.path.expanduser('~')}/.nvm/versions/node/*/bin/{binary}",
        f"/usr/local/bin/{binary}",
    ]:
        if "*" in cand:
            import glob
            hits = glob.glob(cand)
            if hits:
                return hits[0]
            continue
        if cand.startswith("/") and Path(cand).exists():
            return cand
        try:
            r = subprocess.run(["which", cand], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass

    sys.exit(f"[run_eval] Cannot find `{binary}` CLI. Set {env_key} or add to PATH.")


def _extract_session_id(text: str, dialect: str) -> str | None:
    """从 stream-json 头几行提取 session_id。"""
    for line in text.splitlines()[:8]:
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if dialect == "codex":
            if e.get("type") == "thread.started":
                return e.get("thread_id")
        else:
            if e.get("type") == "system" and e.get("subtype") == "init":
                return e.get("session_id")
    return None


def run_prompt(
    prompt: str,
    profile: dict,
    working_dir: Path,
    resume_session: str | None = None,
) -> tuple[str, str | None]:
    """
    按 profile 跑一次 headless CLI，返回 (jsonl_text, session_id)。
    session_id 可传给下一 turn 的 resume。
    """
    binary = find_cli_bin(profile)
    cli_cfg = profile["cli"]
    dialect = cli_cfg.get("event_dialect", "claude")

    if resume_session and cli_cfg.get("resume_args"):
        subcommand = cli_cfg.get("resume_subcommand", [])
        raw_args = subcommand + [
            a.replace("{session_id}", resume_session)
            for a in cli_cfg["resume_args"]
        ]
        cmd = [binary] + raw_args + [prompt]
    else:
        cmd = [binary] + list(cli_cfg.get("args", [])) + [prompt]

    label = f"{binary} (session={resume_session or 'new'})"
    print(f"    ▸ running {label}, cwd={working_dir} ...", flush=True)
    t0 = time.time()
    try:
        r = subprocess.run(
            cmd,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return ("", None)

    elapsed = time.time() - t0
    print(f"    ▸ done in {elapsed:.1f}s (exit={r.returncode}, {len(r.stdout)} bytes stdout)", flush=True)

    session_id = _extract_session_id(r.stdout, dialect)
    return (r.stdout, session_id)


# ── 简易 yaml writer（复用 generate.py 里的思路，独立一份避免循环依赖）────────

def _yaml_scalar(v) -> str:
    if v is True: return "true"
    if v is False: return "false"
    if v is None or v == "": return ""
    s = str(v)
    if s in ("?", "!", "&", "*", "|", ">", "-", "Y", "N", "S") or ":" in s:
        return f'"{s}"'
    return s


def dump_results_yaml(data: dict) -> str:
    """把 run_eval 的结果 dict 序列化为 score.py 能读的 yaml。"""
    lines = []
    lines.append(f"version: 2.0")
    lines.append(f"ide: {_yaml_scalar(data['ide'])}")
    lines.append(f"tester: {_yaml_scalar(data.get('tester', 'run_eval.py'))}")
    lines.append(f"date: {_yaml_scalar(data.get('date', ''))}")
    lines.append(f"cases:")

    for case in data["cases"]:
        lines.append(f"  - case_id: {case['case_id']}")
        if "ide_capabilities_required" in case:
            lines.append(f"    ide_capabilities_required: {json.dumps(case['ide_capabilities_required'])}")
        if "turns" in case:
            lines.append(f"    turns:")
            for t in case["turns"]:
                lines.append(f"    - turn: {t['turn']}")
                lines.append(f"      observations:")
                for k, v in t["observations"].items():
                    lines.append(f"        {k}: {_yaml_scalar(v)}")
        if "observations" in case:
            lines.append(f"    observations:")
            for k, v in case["observations"].items():
                lines.append(f"      {k}: {_yaml_scalar(v)}")
        if "case_level" in case:
            lines.append(f"    case_level:")
            for k, v in case["case_level"].items():
                lines.append(f"      {k}: {_yaml_scalar(v)}")
        notes = case.get("notes", "")
        if notes:
            lines.append(f"    notes: {_yaml_scalar(notes)}")
        else:
            lines.append(f"    notes: ")

    return "\n".join(lines) + "\n"


# ── 主流程 ────────────────────────────────────────────────────────────────

# --probe 时每个 IDE 用的默认便宜模型（可被 --probe-model 覆盖）
PROBE_DEFAULT_MODEL = {
    "claude-code": "haiku",
    "cursor":      "auto",
    "codebuddy":   "claude-haiku-4.5",
    "codex":       None,     # codex 走 -c model=... 覆盖，默认不改
}
PROBE_PROMPT = "respond with just: ok"


def run_probe(ide: str, profile: dict, working_dir: Path, override_model: str | None) -> int:
    """--probe: 发一条最简 prompt 验证 CLI + 事件流解析器 + session_id 提取都工作。
    使用便宜模型避免耗额度。不做任何观察点判定，不写 results.yaml。"""
    print(f"[probe] IDE: {ide}")
    print(f"[probe] working dir: {working_dir}")

    # 复制 profile 并注入 --model 参数
    import copy
    p = copy.deepcopy(profile)
    cli = p.setdefault("cli", {})
    args = list(cli.get("args", []))
    dialect = cli.get("event_dialect", "claude")

    model = override_model or PROBE_DEFAULT_MODEL.get(ide)
    if model:
        if ide == "codex":
            args = ["-c", f'model="{model}"'] + args
        else:
            args = args + ["--model", model]
        print(f"[probe] model: {model}")
    else:
        print(f"[probe] model: <IDE default>")

    cli["args"] = args

    text, sid = run_prompt(PROBE_PROMPT, p, working_dir, resume_session=None)
    n_lines = sum(1 for L in text.splitlines() if L.strip().startswith("{"))
    print(f"[probe] output: {n_lines} JSON line(s), session_id={sid or '<not extracted>'}")

    # 尝试解析
    parsed = parse_transcript(text, dialect=dialect)
    print(f"[probe] parsed: {len(parsed.tool_calls)} tool_use, "
          f"{len(parsed.tool_results)} tool_result, "
          f"{len(parsed.text_blocks)} text block(s)")
    if parsed.result_status:
        print(f"[probe] result: {parsed.result_status}"
              f"{'  error=' + parsed.error if parsed.error else ''}")

    # 事件类型分布
    types: dict[str, int] = {}
    for L in text.splitlines():
        L = L.strip()
        if not L or not L.startswith("{"):
            continue
        try:
            e = json.loads(L)
        except json.JSONDecodeError:
            continue
        t = e.get("type", "?")
        types[t] = types.get(t, 0) + 1
    if types:
        print(f"[probe] event types: {dict(sorted(types.items(), key=lambda x: -x[1]))}")

    # 判定 probe 是否成功：session_id 提取到 + 事件流被解析（result_status 有值）
    ok = bool(sid) and bool(parsed.result_status)
    verdict = "passed" if ok else "FAILED"
    icon = "✓" if ok else "✗"
    detail = f"result={parsed.result_status or '<empty>'}"
    if not sid:
        detail += " · session_id NOT extracted"
    print(f"\n{icon} probe {verdict}: CLI reachable, stream-json parseable  ({detail})")
    return 0 if ok else 1


def run_case(
    case: dict,
    obs_dict: dict,
    ide: str,
    profile: dict,
    ide_caps: set[str],
    working_dir: Path,
    transcript_dir: Path,
    dry_run: bool = False,
    keep_session: bool = False,
) -> dict:
    """
    跑一条 case（可能多轮），返回 results.yaml 里对应 case 的 entry dict。
    每条 case 开跑前会清理 .trtc-session.yaml（除非 keep_session=True 或 dry_run），
    以避免上条 case 的会话状态污染当前 case。case 内部多 turn 之间不清（用 --resume 承接）。
    """
    cid = case["case_id"]
    print(f"\n[{cid}] {case.get('description', '')[:60]}", flush=True)

    dialect = profile.get("cli", {}).get("event_dialect", "claude")

    # 清 session（跨 case，非跨 turn）
    if not (dry_run or keep_session):
        n = clear_sessions(working_dir)
        if n:
            print(f"  ⌫ cleared {n} stale session file(s)", flush=True)

    # case 级能力检查
    req_caps = case.get("ide_capabilities_required", [])
    missing_caps = [c for c in req_caps if c not in ide_caps]
    if missing_caps:
        print(f"  ⊘ IDE lacks capability: {missing_caps} — marking whole case as ?", flush=True)
        entry = {"case_id": cid, "ide_capabilities_required": req_caps, "notes": f"skipped: IDE lacks {missing_caps}"}
        turns = case.get("turns", [])
        if len(turns) == 1:
            expect = turns[0].get("expect", {})
            entry["observations"] = {k: "?" for k in expect if k in obs_dict}
        else:
            entry["turns"] = [
                {"turn": i+1, "observations": {k: "?" for k in t.get("expect", {}) if k in obs_dict}}
                for i, t in enumerate(turns)
            ]
        return entry

    turns = case.get("turns", [])
    entry = {"case_id": cid, "notes": ""}
    session_id = None
    turn_results = []
    all_reasons = []

    for t_idx, turn in enumerate(turns, 1):
        prompt = turn["user"]
        expect = turn.get("expect", {})

        # 跑 prompt 或用 dry-run 假 transcript
        if dry_run:
            print(f"  [turn {t_idx}] DRY-RUN skip: {prompt[:60]}", flush=True)
            transcript_text = ""
        else:
            transcript_text, sid = run_prompt(prompt, profile, working_dir, resume_session=session_id)
            if sid and not session_id:
                session_id = sid
            # 保存 transcript
            tp = transcript_dir / f"{cid}.turn{t_idx}.jsonl"
            tp.write_text(transcript_text)

        transcript = parse_transcript(transcript_text, dialect=dialect)
        n_tools = len(transcript.tool_calls)
        print(f"    ▸ parsed: {n_tools} tool calls, {len(transcript.tool_results)} results", flush=True)

        # 逐个观察点判定
        turn_obs = {}
        for obs_key in expect:
            if obs_key not in obs_dict:
                continue
            # 能力过滤：obs_key 需要的能力 IDE 没有 → 直接 skip
            required = obs_dict[obs_key].get("requires", [])
            if any(c not in ide_caps for c in required):
                turn_obs[obs_key] = "S"
                continue
            verdict, reason = evaluate_observation(obs_key, expect[obs_key], transcript, working_dir)
            turn_obs[obs_key] = verdict
            icon = {"Y": "✓", "N": "✗", "S": "─"}.get(verdict, "?")
            print(f"      {icon} {obs_key}: {verdict}  ({reason[:80]})", flush=True)
            all_reasons.append(f"turn{t_idx}.{obs_key}={verdict}: {reason}")

        turn_results.append({"turn": t_idx, "observations": turn_obs})

    # 组装 entry
    if len(turns) == 1:
        entry["observations"] = turn_results[0]["observations"]
    else:
        entry["turns"] = turn_results

    # case_level_expect 现阶段无自动判定器，全 S
    case_level = case.get("case_level_expect", {})
    if case_level:
        entry["case_level"] = {k: "S" for k in case_level}

    entry["notes"] = f"auto by run_eval.py; {len(turns)} turn(s)"
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2 全自动评测器 (POC, claude-code)")
    parser.add_argument("--ide", default="claude-code",
                        choices=["claude-code", "cursor", "codebuddy", "codex"],
                        help="Target IDE (all 4 supported; behaviour driven by cases.json ide_profiles)")
    parser.add_argument("--cases", default=str(HERE / "cases.json"))
    parser.add_argument("--out-dir", default=str(HERE / "eval-runs" / "latest"))
    parser.add_argument("--case", help="只跑指定的 case_id")
    parser.add_argument("--tags", help="Comma-separated tag filter, e.g. smoke")
    parser.add_argument("--working-dir", default=str(HERE),
                        help="skill 已 npx add 到此目录（默认为 cases.json 所在目录）")
    parser.add_argument("--dry-run", action="store_true",
                        help="不调 CLI；用空 transcript 走一遍解析器（自测）")
    parser.add_argument("--keep-session", action="store_true",
                        help="跑前不清理 .trtc-session.yaml（调试专用；正常不要开）")
    parser.add_argument("--probe", action="store_true",
                        help="发一句最简 prompt 验证事件流能被正确解析，不跑任何 case、不做观察点判定。"
                             " 适合新 IDE 集成 / 额度紧张时快速自检")
    parser.add_argument("--probe-model", default=None,
                        help="--probe 模式下使用的模型；不填则用 IDE 默认（cursor auto / codebuddy haiku 等）")
    parser.add_argument("--model", default=None,
                        help="完整评测使用的模型（CI 便宜档常用：haiku / gpt-4o-mini / claude-haiku-4.5）；"
                             " claude/cursor/codebuddy 走 --model，codex 走 -c model=...")
    args = parser.parse_args()

    if args.dry_run and args.probe:
        sys.exit("[run_eval] --dry-run 与 --probe 互斥")

    cases_path = Path(args.cases)
    if not cases_path.exists():
        sys.exit(f"cases.json not found: {cases_path}")

    with open(cases_path) as f:
        cases_data = json.load(f)

    obs_dict = cases_data.get("obs_keys", {})
    ide_profiles = cases_data.get("ide_profiles", {})
    profile = ide_profiles.get(args.ide)
    if not profile:
        sys.exit(f"IDE profile not found: {args.ide}")

    ide_caps = set(profile.get("capabilities", []))
    working_dir = Path(args.working_dir).expanduser().resolve()

    # ── probe 模式：只验事件流，不跑 case ──────────────────────────
    if args.probe:
        return run_probe(args.ide, profile, working_dir, args.probe_model)

    # ── 完整评测：如果指定了 --model，把模型注入到 profile.cli.args ──
    if args.model:
        import copy
        profile = copy.deepcopy(profile)
        cli = profile.setdefault("cli", {})
        cli_args = list(cli.get("args", []))
        if args.ide == "codex":
            cli_args = ["-c", f'model="{args.model}"'] + cli_args
        else:
            cli_args = cli_args + ["--model", args.model]
        cli["args"] = cli_args
        print(f"[run_eval] model override: {args.model}")

    # 挑 P2 case
    tag_filter = set(args.tags.split(",")) if args.tags else set()
    p2_cases = [
        c for c in cases_data["cases"]
        if c.get("phase") == "p2"
        and (not args.case or c["case_id"] == args.case)
        and (not tag_filter or tag_filter.intersection(c.get("tags", [])))
    ]
    if not p2_cases:
        sys.exit("No P2 cases matched.")

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    transcript_dir = out_dir / "transcripts"
    transcript_dir.mkdir(exist_ok=True)

    print(f"[run_eval] IDE: {args.ide}")
    print(f"[run_eval] working dir: {working_dir}")
    print(f"[run_eval] out dir: {out_dir}")
    print(f"[run_eval] cases: {len(p2_cases)}  {'(DRY-RUN)' if args.dry_run else ''}")

    entries = []
    for case in p2_cases:
        entries.append(run_case(
            case, obs_dict, args.ide, profile, ide_caps,
            working_dir, transcript_dir,
            dry_run=args.dry_run,
            keep_session=args.keep_session,
        ))

    # 写 results yaml
    from datetime import datetime
    yaml_data = {
        "ide": args.ide,
        "tester": "run_eval.py",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "cases": entries,
    }
    yaml_path = out_dir / f"results.{args.ide}.yaml"
    yaml_path.write_text(dump_results_yaml(yaml_data), encoding="utf-8")
    print(f"\n✓ results → {yaml_path}")
    print(f"✓ transcripts → {transcript_dir}")
    print(f"\n下一步:  python3 score.py {yaml_path} --cases {cases_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
