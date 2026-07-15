"""α/β dual-track arbitration tests."""
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.lib.arbitrator import AlphaTool, BetaTool, ToolRegistry


class ArbitratorTests(unittest.TestCase):

    def test_alpha_first_when_both_available(self):
        r = ToolRegistry(default_priority="alpha")
        r.register_alpha(AlphaTool(name="echo", func=lambda **kw: {"track": "alpha", "kw": kw}))
        r.register_beta(BetaTool(name="echo", endpoint="https://example.com"))
        result = r.call("echo", {"x": 1})
        self.assertEqual(result.track, "alpha")
        self.assertTrue(result.ok)
        self.assertEqual(result.fallback_chain, ["alpha"])

    def test_alpha_failure_falls_back_to_beta(self):
        r = ToolRegistry(default_priority="alpha")

        def boom(**_kw):
            raise RuntimeError("alpha down")

        r.register_alpha(AlphaTool(name="echo", func=boom))
        r.register_beta(BetaTool(name="echo", endpoint="https://example.com"))

        def fake_beta(tool, params):
            return {"track": "beta", "ep": tool.endpoint, "params": params}

        result = r.call("echo", {"x": 1}, beta_invoker=fake_beta)
        self.assertEqual(result.track, "beta")
        self.assertTrue(result.ok)
        self.assertEqual(result.fallback_chain, ["alpha", "beta"])

    def test_beta_priority_explicit(self):
        r = ToolRegistry(default_priority="beta")
        r.register_alpha(AlphaTool(name="echo", func=lambda **kw: {"a": True}))
        r.register_beta(BetaTool(name="echo", endpoint="https://example.com"))

        result = r.call("echo", {}, beta_invoker=lambda t, p: {"b": True})
        self.assertEqual(result.track, "beta")

    def test_no_track_available_yields_failure(self):
        r = ToolRegistry()
        result = r.call("nonexistent", {})
        self.assertFalse(result.ok)
        self.assertIn("no track", result.error)

    def test_alpha_only_when_beta_invoker_missing(self):
        r = ToolRegistry()
        r.register_beta(BetaTool(name="x", endpoint="https://example.com"))
        # No beta_invoker provided
        result = r.call("x", {})
        self.assertFalse(result.ok)
        self.assertIn("beta_invoker not provided", result.error)


if __name__ == "__main__":
    unittest.main()
