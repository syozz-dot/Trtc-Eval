"""Tech stack detection + three-tier fallback tests."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.lib import stack_detector as sd
from scripts.lib import degrader as dg


def _mkproj(files: dict) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="stack_"))
    for name, content in files.items():
        p = tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp


class StackDetectorTests(unittest.TestCase):

    def test_react_project(self):
        proj = _mkproj({
            "package.json": json.dumps({"dependencies": {"react": "^18.2.0", "react-dom": "^18.2.0"}}),
        })
        res = sd.detect(proj)
        self.assertEqual(res.primary, "react")
        self.assertIn("react", res.candidates)

    def test_next_priority_over_react(self):
        proj = _mkproj({
            "package.json": json.dumps({"dependencies": {"next": "^14", "react": "^18"}}),
        })
        res = sd.detect(proj)
        self.assertEqual(res.primary, "next")

    def test_express_node_backend(self):
        proj = _mkproj({"package.json": json.dumps({"dependencies": {"express": "^4"}})})
        self.assertEqual(sd.detect(proj).primary, "express")

    def test_spring_boot_pom(self):
        proj = _mkproj({"pom.xml": "<artifactId>spring-boot-starter-web</artifactId>"})
        self.assertEqual(sd.detect(proj).primary, "spring-boot")

    def test_python_fastapi_priority_over_flask(self):
        proj = _mkproj({"requirements.txt": "fastapi==0.110\nflask==3.0\n"})
        self.assertEqual(sd.detect(proj).primary, "fastapi")

    def test_unknown_returns_none(self):
        proj = _mkproj({"random.txt": "hello"})
        self.assertIsNone(sd.detect(proj).primary)

    def test_match_adapter(self):
        adapters = [
            {"tech_stack": ["react", "vue"], "adapter": "frontend-spa"},
            {"tech_stack": ["express"], "adapter": "node-backend"},
        ]
        self.assertEqual(sd.match_adapter("react", adapters), "frontend-spa")
        self.assertEqual(sd.match_adapter("express", adapters), "node-backend")
        self.assertIsNone(sd.match_adapter("unknown", adapters))


class DegraderTests(unittest.TestCase):

    def test_l1_when_match_and_codegen_ok(self):
        d = dg.decide("react", "frontend-spa", True)
        self.assertEqual(d.level, dg.DegradeLevel.L1_AUTO)

    def test_l2_when_match_but_codegen_failed(self):
        fb = {"guided_templates": ["x.md"]}
        d = dg.decide("react", "frontend-spa", False, fallback=fb, code_gen_error="conflict")
        self.assertEqual(d.level, dg.DegradeLevel.L2_GUIDED)
        self.assertIn("x.md", d.artifacts)
        self.assertIn("conflict", d.reason)

    def test_l3_when_no_tech_stack(self):
        fb = {"manual_api": {"rest_endpoint": "/api/v1", "sdk_packages": [{"npm": "x"}]}}
        d = dg.decide(None, None, False, fallback=fb)
        self.assertEqual(d.level, dg.DegradeLevel.L3_MANUAL)
        self.assertTrue(any("rest_endpoint:/api/v1" in a for a in d.artifacts))
        self.assertTrue(any("sdk:npm:x" in a for a in d.artifacts))

    def test_l3_when_stack_known_but_no_adapter(self):
        d = dg.decide("svelte", None, False, fallback={"manual_api": {}})
        self.assertEqual(d.level, dg.DegradeLevel.L3_MANUAL)
        self.assertIn("no adapter for tech_stack=svelte", d.reason)

    def test_channel_matrix_has_16_rows(self):
        rows = dg.channel_combinations_matrix()
        self.assertEqual(len(rows), 16)
        verdicts = {r["verdict"] for r in rows}
        self.assertIn("silent_wait", verdicts)


if __name__ == "__main__":
    unittest.main()
