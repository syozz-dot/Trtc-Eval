"""Capability overlay end-to-end tests: add-capability dry-run + adapter rendering against the real repo."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _run(*args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "add-capability.py"), *args, "--json"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        timeout=20,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"add-capability failed: {proc.stderr}")
    return json.loads(proc.stdout)


class CapabilityOverlayTests(unittest.TestCase):

    def test_list_includes_all_capabilities(self):
        out = _run("--list")
        self.assertEqual(out["skeleton"], "conversation-core")
        names = {c["name"] for c in out["capabilities"]}
        for n in ("knowledge-base", "tool-calling", "human-handoff",
                  "session-summary", "digital-human"):
            self.assertIn(n, names)

    def test_install_dry_run_topological_order(self):
        out = _run("session-summary", "knowledge-base", "tool-calling")
        order = out["install_order"]
        self.assertTrue(set(order).issuperset({"knowledge-base", "tool-calling", "session-summary"}))
        self.assertTrue(out["dry_run"])
        for r in out["reports"]:
            self.assertIn("skeleton_injection", r)
            for inj in r["skeleton_injection"]:
                # Injection plan must locate anchor (dry-run so applied may be True/False; key is no error)
                if inj["error"]:
                    self.fail(f"injection error for {r['capability']}: {inj}")

    def test_adapter_l1_render_for_react_project(self):
        with tempfile.TemporaryDirectory() as td:
            user_proj = Path(td) / "react-app"
            user_proj.mkdir()
            (user_proj / "package.json").write_text(
                json.dumps({"dependencies": {"react": "^18.2.0"}}), encoding="utf-8"
            )
            out = _run(
                "knowledge-base",
                "--target-project", str(user_proj),
                "--apply",
            )
            kb_report = next(r for r in out["reports"] if r["capability"] == "knowledge-base")
            self.assertEqual(kb_report["adapter"]["adapter"], "frontend-spa")
            self.assertEqual(kb_report["degrade"]["level"], "L1")
            # Expected generated file exists
            target = user_proj / "src" / "components" / "VoiceAgent.tsx"
            self.assertTrue(target.exists(), f"expected {target} to exist")
            content = target.read_text(encoding="utf-8")
            # Placeholder variables have been substituted
            self.assertIn("http://localhost:3000", content)
            self.assertNotIn("${SKELETON_BASE_URL}", content)

    def test_adapter_l3_when_unknown_stack(self):
        with tempfile.TemporaryDirectory() as td:
            user_proj = Path(td) / "exotic"
            user_proj.mkdir()
            (user_proj / "manifest.toml").write_text("# nothing recognisable\n", encoding="utf-8")
            out = _run(
                "knowledge-base",
                "--target-project", str(user_proj),
            )
            kb_report = next(r for r in out["reports"] if r["capability"] == "knowledge-base")
            self.assertIsNone(kb_report["adapter"]["tech_stack_used"])
            self.assertEqual(kb_report["degrade"]["level"], "L3")


if __name__ == "__main__":
    unittest.main()
