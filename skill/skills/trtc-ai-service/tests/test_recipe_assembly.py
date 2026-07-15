"""Phase 3 Stage 6: scenarios/* recipe static validation + Path B Jinja template rendering tests.

Coverage targets:
- Path A: scenarios/customer-service/recipe.yaml has valid structure and key fields present
- Path B: output-templates/recipe.yaml.j2 rendered with 4 typical Q1~Q4 answer sets produces valid YAML with correct field linkage
- ui_overlay referenced subdirectories widget-floating / admin-board all physically exist
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_SCEN = _ROOT / "scenarios"
_RECIPE_A = _SCEN / "customer-service" / "recipe.yaml"
_TEMPLATE = _SCEN / "custom-builder" / "output-templates" / "recipe.yaml.j2"


class CustomerServiceRecipeTests(unittest.TestCase):
    """Path A default recipe static structure validation."""

    def setUp(self):
        self.assertTrue(_RECIPE_A.exists(), f"recipe.yaml not found: {_RECIPE_A}")
        self.recipe = yaml.safe_load(_RECIPE_A.read_text(encoding="utf-8"))

    def test_top_level_kind_and_api_version(self):
        self.assertEqual(self.recipe.get("kind"), "Recipe")
        self.assertEqual(self.recipe.get("apiVersion"), "ai-customer-service/v1")

    def test_install_capabilities_contain_kb_and_handoff(self):
        installs = self.recipe["capabilities"]["install"]
        names = {c["name"] for c in installs}
        self.assertIn("knowledge-base", names)
        self.assertIn("human-handoff", names)
        # adapter field must be explicitly given (out-of-box experience relies on mock / local_queue)
        for c in installs:
            self.assertIn("adapter", c)
            self.assertIn("env", c)

    def test_excluded_capability_is_digital_human(self):
        excluded = self.recipe["capabilities"].get("excluded") or []
        names = {c["name"] for c in excluded}
        self.assertIn("digital-human", names)

    def test_ui_overlay_layers_reference_real_dirs(self):
        layers = self.recipe["ui_overlay"]["layers"]
        ui_root = _SCEN / "customer-service" / "ui"
        for layer in layers:
            sub = ui_root / layer["source"]
            self.assertTrue(sub.is_dir(), f"missing UI overlay source dir: {sub}")

    def test_post_assembly_health_check_url(self):
        hc = self.recipe["post_assembly"]["health_check"]
        self.assertEqual(hc["url"], "http://localhost:3000/api/v1/health")

    def test_design_locks_dark_no_emoji(self):
        d = self.recipe["design"]
        self.assertEqual(d["theme"], "dark")
        self.assertFalse(d["emoji_in_ui"])


# ---------------------------------------------------------------------------
# Path B: Jinja2 template rendering (falls back to substring checks if Jinja2 unavailable)
# ---------------------------------------------------------------------------
try:
    import jinja2  # type: ignore
    _HAS_JINJA = True
except ImportError:  # pragma: no cover
    _HAS_JINJA = False


class CustomBuilderTemplateStructureTests(unittest.TestCase):
    """The key Jinja branch literals must exist in the template (does not depend on Jinja2 engine)."""

    def setUp(self):
        self.assertTrue(_TEMPLATE.exists(), f"template not found: {_TEMPLATE}")
        self.text = _TEMPLATE.read_text(encoding="utf-8")

    def test_io_modality_branches_present(self):
        for modality in ("text_only", "text_with_tts", "omni", "voice_only"):
            self.assertIn(modality, self.text)

    def test_ui_form_branches_present(self):
        for form in ("floating", "fullscreen", "headless"):
            self.assertIn(form, self.text)

    def test_capability_branches_present(self):
        for cap in (
            "knowledge-base",
            "human-handoff",
            "tool-calling",
            "session-summary",
        ):
            self.assertIn(cap, self.text)

    def test_excludes_digital_human(self):
        self.assertIn("digital-human", self.text)
        self.assertIn("excluded", self.text)


@unittest.skipUnless(_HAS_JINJA, "jinja2 not installed; skip render assertions")
class CustomBuilderTemplateRenderTests(unittest.TestCase):
    """Jinja2 渲染后的 YAML 应可被 yaml.safe_load 解析，且关键字段按 Q 答联动。"""

    def _render(self, **ctx) -> str:
        env = jinja2.Environment(  # type: ignore[name-defined]
            keep_trailing_newline=True,
            trim_blocks=False,
            lstrip_blocks=False,
        )
        tpl = env.from_string(_TEMPLATE.read_text(encoding="utf-8"))
        return tpl.render(**ctx)

    def test_render_text_with_tts_floating_kb_only(self):
        out = self._render(
            business_desc="我们是一家咖啡品牌的电商客服",
            business_name="ACME",
            io_modality="text_with_tts",
            ui_form="floating",
            extra_capabilities=["knowledge-base"],
        )
        data = yaml.safe_load(out)
        self.assertEqual(data["apiVersion"], "ai-customer-service/v1")
        # Q2 linkage
        self.assertFalse(data["runtime_modality"]["voice_input"])
        self.assertTrue(data["runtime_modality"]["voice_output"])
        # Q3 联动
        self.assertTrue(data["ui"]["overlay_required"])
        # human-handoff not selected → admin-board layer not present
        layer_sources = [l["source"] for l in data["ui"]["ui_overlay"]["layers"]]
        self.assertIn("widget-floating", layer_sources)
        self.assertNotIn("admin-board", layer_sources)
        # Q4: only knowledge-base installed
        installed_names = {c["name"] for c in data["capabilities"]["install"]}
        self.assertEqual(installed_names, {"knowledge-base"})

    def test_render_omni_fullscreen_with_handoff(self):
        out = self._render(
            business_desc="车企售后客服",
            business_name="XYZ",
            io_modality="omni",
            ui_form="fullscreen",
            extra_capabilities=["knowledge-base", "human-handoff"],
        )
        data = yaml.safe_load(out)
        self.assertTrue(data["runtime_modality"]["voice_input"])
        self.assertTrue(data["runtime_modality"]["text_input"])
        # human-handoff selected → admin-board layer should exist
        layer_sources = [l["source"] for l in data["ui"]["ui_overlay"]["layers"]]
        self.assertIn("admin-board", layer_sources)
        installed_names = {c["name"] for c in data["capabilities"]["install"]}
        self.assertEqual(installed_names, {"knowledge-base", "human-handoff"})

    def test_render_headless_no_overlay(self):
        out = self._render(
            business_desc="纯 API 后端客服",
            business_name="BackOnly",
            io_modality="text_only",
            ui_form="headless",
            extra_capabilities=[],
        )
        data = yaml.safe_load(out)
        self.assertFalse(data["ui"]["overlay_required"])
        self.assertIsNone(data["ui"]["ui_overlay"])
        # User selected no capabilities → install list is empty
        self.assertEqual(data["capabilities"]["install"], [])


if __name__ == "__main__":
    unittest.main()
