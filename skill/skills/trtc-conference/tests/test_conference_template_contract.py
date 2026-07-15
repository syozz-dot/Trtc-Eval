from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCENARIO = ROOT / "knowledge-base" / "scenarios" / "conference" / "medical" / "1v1-video-consultation.md"
PLAYBOOK = ROOT / "skills" / "trtc-conference" / "playbooks" / "medical-quickstart.md"
TEMPLATE_DIR = ROOT / "skills" / "trtc-conference" / "templates" / "medical-consultation"
def test_medical_template_owner_path_exists() -> None:
    assert TEMPLATE_DIR.exists()
    assert (TEMPLATE_DIR / "package.json").exists()
    assert (TEMPLATE_DIR / "src" / "App.vue").exists()


def test_medical_scenario_frontmatter_points_to_conference_owned_template_path() -> None:
    text = SCENARIO.read_text()
    assert "path: skills/trtc-conference/templates/medical-consultation/" in text


def test_medical_quickstart_playbook_uses_owner_template_path() -> None:
    text = PLAYBOOK.read_text()
    assert "`../templates/medical-consultation/`" in text
    assert "完整复制到目标目录" in text
    assert "integration_path: medical-quickstart" in text
