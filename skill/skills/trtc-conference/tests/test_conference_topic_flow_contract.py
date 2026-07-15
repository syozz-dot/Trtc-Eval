from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONFERENCE_TOPIC = ROOT / "skills" / "trtc-conference" / "flows" / "topic.md"
CONFERENCE_ONBOARDING = ROOT / "skills" / "trtc-conference" / "flows" / "onboarding.md"
OFFICIAL_ROOMKIT_PLAYBOOK = ROOT / "skills" / "trtc-conference" / "playbooks" / "official-roomkit.md"


def _section(text: str, start: str, end: str | None = None) -> str:
    begin = text.index(start)
    finish = text.index(end, begin) if end else len(text)
    return text[begin:finish]


def test_conference_topic_flow_carries_required_policy_sections() -> None:
    text = CONFERENCE_TOPIC.read_text()

    required_sections = [
        "## Step 1: Pre-flight and scenario context",
        "## Step 1.5: Coverage decision gate",
        "## Step 1.6: Collect business decisions",
        "## Step 2: Check prerequisites",
        "## Step 3: Slice loop and execution policy",
        "### 3.1 auto_advance_policy gate",
        "### 3.2 状态机是共享机制，不得重写",
        "### 3.3 conference 的 scope 与 unit 规则",
        "### 3.4 conference code generation rules（owner-level）",
        "### 3.5 apply result handling and progression",
        "### 3.6 `ui_mode` owner rules（self-contained）",
        "### 3.7 planned slices, mid-flow facts, debugging",
        "## Step 4: Verification and finalize",
    ]

    assert "Conference Topic Flow" in text
    assert "coverage_decided" in text
    missing = [section for section in required_sections if section not in text]
    assert not missing, f"conference topic self-contained sections missing: {missing}"
    assert "G1: Copy from slices, don't improvise" in text
    assert "G8: Respect `business_decisions` for every registry slice" in text
    assert "ui_mode = official-roomkit" in text
    assert "ui_mode = headless" in text
    assert "STATE-MACHINE-GUIDE.md" in text
    assert "../../trtc/tools/apply.py" in text
    assert "python3 -m tools.apply --slice <id>" in text
    assert "python3 -m tools.apply --unit <id>" in text
    assert "RUNTIME.md" in text
    assert "finalize_session.py" in text


def test_conference_topic_step_15_uses_coverage_decided_as_the_only_ownership_signal() -> None:
    text = CONFERENCE_TOPIC.read_text()
    section = _section(text, "## Step 1.5: Coverage decision gate", "## Step 1.6: Collect business decisions")

    assert "coverage_decided = true" in section
    assert "coverage_decided = false" in section
    assert "coverage_decided = null" in section
    assert "这个字段是 coverage ownership 的唯一判据" in section
    assert "topic 不从 `confirmed_plan`" in section
    assert "`enhancement_level` 或 handoff 方式反推 ownership" in section


def test_conference_topic_step_15_preserves_general_conference_user_choice() -> None:
    text = CONFERENCE_TOPIC.read_text()
    section = _section(text, "## Step 1.5: Coverage decision gate", "## Step 1.6: Collect business decisions")

    assert "general-conference" in section
    assert "coverage_decided = false" in section
    assert "展示骨架能力与可选模块" in section
    assert "写入最终 `confirmed_plan`，并**同时**把 `coverage_decided` 翻成 `true`" in section


def test_conference_topic_step_15_skips_reasking_when_onboarding_already_decided_coverage() -> None:
    text = CONFERENCE_TOPIC.read_text()
    section = _section(text, "## Step 1.5: Coverage decision gate", "## Step 1.6: Collect business decisions")

    assert "1v1-video-consultation" in section
    assert "本 phase 不得重新问 coverage" in section
    assert "integrate-feature" in section
    assert "本 phase 不得扩成更大场景" in section


def test_conference_topic_flow_is_no_longer_shared_topic_dependent() -> None:
    text = CONFERENCE_TOPIC.read_text()

    assert "../../trtc-topic/SKILL.md" not in text
    assert "共享机制章节" not in text
    assert "Phase 1 过渡期" not in text


def test_conference_onboarding_handoff_uses_local_topic_flow() -> None:
    text = CONFERENCE_ONBOARDING.read_text()

    assert "flows/topic.md" in text
    assert "../../trtc-topic/SKILL.md" not in text


def test_conference_domain_skill_ui_mode_branches_do_not_expose_roomkit_for_medical_or_planned_scenarios() -> None:
    text = (ROOT / "skills" / "trtc-conference" / "SKILL.md").read_text()

    medical_existing = _section(text, "### 分支 2：医疗老项目（fail-closed，RoomKit 不适用）", "### 分支 3：planned scenario（fail-closed）")
    planned = _section(text, "### 分支 3：planned scenario（fail-closed）", "### 分支 4：通用会议")
    general = _section(text, "### 分支 4：通用会议", "**将 `ui_mode` 搭车写入 session，不单独触发一次 Write。**")

    assert "不出现 RoomKit 选项" in medical_existing
    assert "`ui_mode = headless`" in medical_existing
    assert "`integration_path = topic`" in medical_existing
    assert "不出现 RoomKit 选项" in planned
    assert "`ui_mode = headless`" in planned
    assert "`integration_path = topic`" in planned
    assert "`ui_mode = official-roomkit`" in general
    assert "`integration_path = official-roomkit`" in general


def test_conference_domain_skill_exposes_direct_route_bootstrap() -> None:
    text = (ROOT / "skills" / "trtc-conference" / "SKILL.md").read_text()

    assert "## Direct-Route Bootstrap" in text
    assert "flow enter --phase topic --product conference --platform web" in text
    assert "python3 -m tools.session create --product conference --platform web --intent integrate-scenario" in text
    assert "coverage_decided=false" in text
    assert "integration_path = topic" in text
    assert "不要手动编辑 `.trtc-session.yaml`" in text


def test_dispatcher_routes_conference_topic_through_domain_skill() -> None:
    text = (ROOT / "skills" / "trtc" / "SKILL.md").read_text()

    assert "../trtc-conference/SKILL.md" in text
    assert "trtc-topic" not in text
    assert "dispatcher → conference domain skill → onboarding/topic flow" in text


def test_conference_official_roomkit_rules_support_react_and_vue3() -> None:
    topic = CONFERENCE_TOPIC.read_text()
    playbook = OFFICIAL_ROOMKIT_PLAYBOOK.read_text()

    assert "@tencentcloud/roomkit-web-react" in topic
    assert "tuikit-atomicx-react" in topic
    assert "@tencentcloud/uikit-base-component-react" in topic
    assert "React 项目不得生成 Vue SFC" in topic

    assert "依赖含 `react` / `next` 时生成 React 版本" in playbook
    assert "@tencentcloud/roomkit-web-react" in playbook
    assert "tuikit-atomicx-react" in playbook
    assert "React 项目不得出现 `@tencentcloud/roomkit-web-vue3`" in playbook
