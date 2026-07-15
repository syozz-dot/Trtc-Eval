from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
INDEX = ROOT / "knowledge-base" / "conference" / "web" / "index.yaml"
OFFICIAL_ROOMKIT_API = ROOT / "knowledge-base" / "slices" / "conference" / "web" / "official-roomkit-api.md"


def _slice_map() -> dict[str, dict]:
    data = yaml.safe_load(INDEX.read_text())
    return {item["id"]: item for item in data["slices"]}


def test_verified_conference_web_index_entries_have_no_todo_markers() -> None:
    text = INDEX.read_text()

    assert "conference/official-roomkit-login-ui" in text
    assert "conference/webinar-interaction" in text
    assert "conference/ai-tools" in text
    assert "TODO: tags/description 未经文件验证" not in text


def test_verified_conference_web_index_entries_match_slice_scope() -> None:
    slices = _slice_map()

    roomkit = slices["conference/official-roomkit-login-ui"]
    webinar = slices["conference/webinar-interaction"]
    ai_tools = slices["conference/ai-tools"]

    assert "layout" in roomkit["tags"]
    assert "LoginPanel" in roomkit["tags"]
    assert "凭证提示" in roomkit["description"]
    assert "React" in roomkit["tags"]

    assert "requestToOpenDevice" in webinar["tags"]
    assert "barrage" in webinar["tags"]
    assert "主持审批" in webinar["description"]

    assert "subtitle" in ai_tools["tags"]
    assert "translation" in ai_tools["tags"]
    assert "实时转写" in ai_tools["description"]


def test_official_roomkit_api_documents_react_package_surface() -> None:
    text = OFFICIAL_ROOMKIT_API.read_text()
    slices = _slice_map()
    api_entry = slices["conference/official-roomkit-api"]

    assert "roomkit-web-react" in api_entry["keywords"]
    assert "React" in api_entry["tags"]
    assert "@tencentcloud/roomkit-web-react" in text
    assert "tuikit-atomicx-react" in text
    assert "@tencentcloud/uikit-base-component-react" in text
    assert "完整代码示例（React）" in text
    assert "不要在 React 项目中生成 Vue SFC" in text
