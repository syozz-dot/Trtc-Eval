"""Manifest parsing / topological order / circular dependency / version conflict / unknown injection point tests."""
import os
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.lib import manifest_resolver as mr


def _mf(name, deps=(), inj=(), ext=(), typ="capability", version="1.0.0"):
    return mr.Manifest(
        name=name, version=version, type=typ,
        dependencies=[mr.DependencySpec(d if isinstance(d, str) else d[0],
                                        d[1] if isinstance(d, tuple) else "*") for d in deps],
        injection_points=list(inj),
        extensions=list(ext),
    )


class ManifestResolverTests(unittest.TestCase):

    def setUp(self):
        self.skeleton = _mf(
            "conversation-core", typ="skeleton",
            inj=[
                {"id": "agent.before_start", "target": "src/agent.py", "position": "before:start_agent"},
                {"id": "agent.after_start", "target": "src/agent.py", "position": "after:start_agent"},
            ],
        )

    def test_topological_order_with_skeleton_first(self):
        a = _mf("cap-a", deps=["conversation-core"])
        b = _mf("cap-b", deps=["conversation-core", "cap-a"])
        graph = mr.resolve([a, self.skeleton, b])
        self.assertEqual(graph.skeleton.name, "conversation-core")
        self.assertEqual(graph.order[0], "conversation-core")
        # b must come after a
        self.assertGreater(graph.order.index("cap-b"), graph.order.index("cap-a"))

    def test_circular_dependency_detected(self):
        a = _mf("cap-a", deps=["cap-b", "conversation-core"])
        b = _mf("cap-b", deps=["cap-a", "conversation-core"])
        with self.assertRaises(mr.CircularDependencyError):
            mr.resolve([self.skeleton, a, b])

    def test_unknown_injection_point_rejected(self):
        bad = _mf(
            "cap-x",
            deps=["conversation-core"],
            ext=[{"inject_at": "no.such.point"}],
        )
        with self.assertRaises(mr.UnknownInjectionPointError):
            mr.resolve([self.skeleton, bad])

    def test_known_injection_point_accepted(self):
        ok = _mf(
            "cap-y",
            deps=["conversation-core"],
            ext=[{"inject_at": "agent.before_start"}],
        )
        graph = mr.resolve([self.skeleton, ok])
        self.assertIn("cap-y", graph.order)

    def test_version_conflict_blocked(self):
        strict = _mf("cap-z", deps=[("conversation-core", ">=2.0.0")])
        with self.assertRaises(mr.VersionConflictError):
            mr.resolve([self.skeleton, strict])

    def test_semver_caret_compatibility(self):
        self.assertTrue(mr.satisfies("1.4.2", "^1.0.0"))
        self.assertFalse(mr.satisfies("2.0.0", "^1.0.0"))
        self.assertTrue(mr.satisfies("1.4.0", ">=1.0.0,<2.0.0"))

    def test_skeleton_uniqueness(self):
        s2 = _mf("another-skeleton", typ="skeleton")
        with self.assertRaises(mr.ManifestError):
            mr.resolve([self.skeleton, s2])

    def test_real_project_capabilities_resolve(self):
        """The 6 capabilities in the real repo should all resolve correctly."""
        manifests = mr.discover_manifests(_ROOT / "capabilities")
        self.assertGreaterEqual(len(manifests), 6)
        graph = mr.resolve(manifests)
        self.assertEqual(graph.order[0], "conversation-core")
        for n in ("knowledge-base", "tool-calling", "human-handoff",
                  "session-summary", "digital-human"):
            self.assertIn(n, graph.order)
            self.assertGreater(graph.order.index(n), graph.order.index("conversation-core"))


if __name__ == "__main__":
    unittest.main()
