from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ONBOARDING = ROOT / "skills" / "trtc-conference" / "flows" / "onboarding.md"


def _read() -> str:
    return ONBOARDING.read_text()


def _section(text: str, start: str, end: str | None = None) -> str:
    begin = text.index(start)
    finish = text.index(end, begin) if end else len(text)
    return text[begin:finish]


def test_conference_onboarding_uses_tools_session_protocol() -> None:
    text = _read()

    assert "不得直接编辑 `.trtc-session.yaml`" in text, (
        "conference onboarding must explicitly forbid direct .trtc-session.yaml edits"
    )
    assert "exit code 3" in text and "CAS 冲突" in text, (
        "conference onboarding must document CAS conflict retry behavior"
    )
    assert "python3 -m tools.session read --field state_version --with-version" in text, (
        "conference onboarding must show the CAS read-before-write protocol"
    )
    assert "python3 -m tools.session write-batch" in text, (
        "conference onboarding must mutate session state via write-batch"
    )


def test_conference_onboarding_declares_react_support() -> None:
    text = _read()

    assert "Conference Web onboarding 已支持 Vue3 与 React 项目" in text
    assert "@tencentcloud/roomkit-web-react" in text
    assert "tuikit-atomicx-react" in text
    assert "不得把 React 项目降级为“不支持”或强制改成 Vue3" in text


def test_conference_onboarding_completed_session_cleanup_contract() -> None:
    text = _read()
    section = _section(text, "## 入口检查", "## 路径一：integrate-scenario")

    assert "status = completed" in section
    assert "python3 -m tools.session reopen-add-feature" in section
    assert "execution_queue/current_execution_* / completed_steps / confirmed_plan" in section
    assert "python3 -m tools.session reset" in section
    assert "dispatcher 重新评估当前会话上下文" in section


def test_conference_onboarding_1v1_writes_fixed_coverage_before_topic() -> None:
    text = _read()
    section = _section(text, "- **1v1-video-consultation**", "- **general-conference**")

    assert "slice 集合固定，无可选项" in section
    assert '"coverage_decided": true' in section
    assert '"confirmed_plan": <场景文件 slices 全集 JSON array>' in section
    assert "topic 不再重复问 coverage" in section


def test_conference_onboarding_general_conference_defers_coverage_choice_to_topic() -> None:
    text = _read()
    section = _section(text, "- **general-conference**", "- **无 active_scenario**")

    assert "onboarding **不写 confirmed_plan**" in section
    assert '"active_scenario": "general-conference", "coverage_decided": false' in section
    assert "topic Step 1.5 负责" in section


def test_conference_onboarding_4c_defaults_to_general_conference_with_pending_coverage() -> None:
    text = _read()
    section = _section(
        text,
        "- **无 active_scenario**",
        "`coverage_decided` 是 coverage ownership 的唯一显式标记：",
    )

    assert '"active_scenario": "general-conference", "coverage_decided": false' in section
    assert "本轮按通用会议场景处理，但 coverage 尚未决策" in section
    assert "topic Step 1.5 必须执行" in section


def test_conference_onboarding_integrate_feature_writes_single_slice_plan() -> None:
    text = _read()
    section = _section(text, "## 路径二：integrate-feature")

    assert 'tools.search slices --product conference --query "<用户描述>" --platform web' in section
    assert '"coverage_decided": true, "confirmed_plan": ["<用户确认后的 slice>"]' in section
    assert "topic Step 1.5 不会再问 coverage" in section


def test_conference_onboarding_does_not_instruct_manual_yaml_edits() -> None:
    text = _read()
    banned_phrases = [
        "直接改 YAML",
        "直接更新 `.trtc-session.yaml`",
        "手动修改 `.trtc-session.yaml`",
        "打开 `.trtc-session.yaml` 并修改",
    ]
    found = [phrase for phrase in banned_phrases if phrase in text]
    assert not found, (
        f"conference onboarding still contains manual-YAML anti-patterns: {found}"
    )
    assert "不得直接编辑 `.trtc-session.yaml`" in text, (
        "conference onboarding should explicitly ban direct session-file edits"
    )
