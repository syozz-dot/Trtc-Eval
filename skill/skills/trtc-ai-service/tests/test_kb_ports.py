"""Phase 3 Stage 6: knowledge-base capability ports/adapters unit tests.

Coverage targets:
- LocalJsonKbClient: reload / search (TF-IDF) / upsert / delete + stats
- MockKbClient: 5 pre-seeded demo FAQ entries + keyword search hits
- DefaultRestKbClient: base_url security validation + search/list_all via HTTP passthrough
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Isolated import: clean src.* cache (avoid conflict with same-named src in test_handoff_ports)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_KB = _ROOT / "capabilities" / "knowledge-base"

for _name in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
    del sys.modules[_name]
sys.path[:] = [p for p in sys.path if "/capabilities/" not in p]
sys.path.insert(0, str(_KB))

import importlib  # noqa: E402

_models = importlib.import_module("src.core.models")
FaqEntry = _models.FaqEntry

from src.adapters.local_json import LocalJsonKbClient  # noqa: E402
from src.adapters.mock import MockKbClient  # noqa: E402
# 预先导入 default_rest（KB 版本）并固化引用，
# 避免后续测试运行时 ``src`` 已被替换为 HH 命名空间
from src.adapters import default_rest as _kb_default_rest  # noqa: E402

DefaultRestKbClient = _kb_default_rest.DefaultRestKbClient


class LocalJsonAdapterTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_path = Path(self._tmp.name) / "faq.json"
        self.data_path.write_text(
            json.dumps(
                [
                    {
                        "id": "kb_refund",
                        "question": "退款政策是什么？",
                        "answer": "支持 7 天无理由退款",
                        "keywords": ["退款", "退货", "refund"],
                    },
                    {
                        "id": "kb_ship",
                        "question": "物流多久送达？",
                        "answer": "全国 3-5 天送达",
                        "keywords": ["物流", "发货"],
                    },
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.client = LocalJsonKbClient(
            data_file=self.data_path, min_score=0.0, top_k=5
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_reload_loads_entries(self):
        self.assertEqual(len(self.client.list_all()), 2)
        stats = self.client.stats()
        self.assertEqual(stats.backend, "local_json")
        self.assertEqual(stats.entry_count, 2)
        self.assertIsNotNone(stats.loaded_at)

    def test_search_hits_by_keyword(self):
        hits = self.client.search("退款", top_k=3)
        self.assertTrue(len(hits) >= 1)
        self.assertEqual(hits[0].entry.id, "kb_refund")
        # score should be > 0
        self.assertGreater(hits[0].score, 0.0)

    def test_search_returns_empty_for_blank_query(self):
        self.assertEqual(self.client.search(""), [])
        self.assertEqual(self.client.search("   "), [])

    def test_upsert_persists_to_disk(self):
        new_entry = FaqEntry(
            id="kb_invoice",
            question="如何开发票？",
            answer="下单时勾选需要发票",
            keywords=["发票"],
        )
        self.client.upsert(new_entry)
        self.assertEqual(len(self.client.list_all()), 3)

        # 真正落盘了：重读文件
        on_disk = json.loads(self.data_path.read_text(encoding="utf-8"))
        ids = {e["id"] for e in on_disk}
        self.assertIn("kb_invoice", ids)

    def test_upsert_updates_existing(self):
        updated = FaqEntry(
            id="kb_refund",
            question="退款政策（已更新）",
            answer="支持 14 天无理由退款",
            keywords=["退款"],
        )
        self.client.upsert(updated)
        items = self.client.list_all()
        self.assertEqual(len(items), 2)  # 总数不变
        kept = next(e for e in items if e.id == "kb_refund")
        self.assertIn("已更新", kept.question)

    def test_delete_removes_entry(self):
        ok = self.client.delete("kb_ship")
        self.assertTrue(ok)
        self.assertEqual(len(self.client.list_all()), 1)
        # Non-existent id returns False
        self.assertFalse(self.client.delete("nonexistent"))


class MockKbAdapterTests(unittest.TestCase):

    def test_seed_five_demo_entries(self):
        c = MockKbClient(seed_demo_data=True)
        items = c.list_all()
        self.assertGreaterEqual(len(items), 5)
        ids = {e.id for e in items}
        for required in ("demo_refund", "demo_logistics", "demo_invoice"):
            self.assertIn(required, ids)

    def test_search_hits_chinese_keyword(self):
        c = MockKbClient(seed_demo_data=True)
        hits = c.search("物流")
        self.assertTrue(any(h.entry.id == "demo_logistics" for h in hits))

    def test_seed_disable(self):
        c = MockKbClient(seed_demo_data=False)
        self.assertEqual(c.list_all(), [])


class DefaultRestKbAdapterSecurityTests(unittest.TestCase):

    def test_https_public_allowed(self):
        c = DefaultRestKbClient(base_url="https://kb.example.com")
        self.assertTrue(c._base.startswith("https://"))

    def test_localhost_http_allowed(self):
        c = DefaultRestKbClient(base_url="http://127.0.0.1:9090")
        self.assertIn("127.0.0.1", c._base)

    def test_private_network_denied(self):
        for url in ("https://10.1.1.1", "https://192.168.1.5"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    DefaultRestKbClient(base_url=url)

    def test_search_calls_post(self):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "hits": [
                {
                    "entry": {
                        "id": "1",
                        "question": "退款？",
                        "answer": "7 天无理由",
                        "keywords": ["退款"],
                    },
                    "score": 0.85,
                }
            ]
        }
        c = DefaultRestKbClient(base_url="https://kb.example.com", token="tok")
        with patch.object(c._session, "post", return_value=fake_resp) as p:
            hits = c.search("退款", top_k=3)

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].entry.id, "1")
        # Request URL path
        args, kwargs = p.call_args
        self.assertTrue(args[0].endswith("/faq/search"))
        self.assertEqual(kwargs["json"]["query"], "退款")
        self.assertEqual(kwargs["json"]["top_k"], 3)


if __name__ == "__main__":
    unittest.main()
