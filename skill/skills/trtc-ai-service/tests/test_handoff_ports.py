"""Phase 3 Stage 6: human-handoff capability ports/adapters unit tests.

Coverage targets:
- LocalQueueHandoffClient: FIFO queue + auto-connect + cancel / status transitions
- MockHandoffClient: pre-seeded demo data (_seed three tickets) + list_tickets
- DefaultRestHandoffClient: base_url security validation (private network denied) + HTTP path calls + passthrough responses

Note: This test file cleans up stale ``src.*`` modules from sys.modules before imports
to avoid conflicts with the same-named ``src`` package in ``test_kb_ports.py``;
KB tests likewise self-clean.
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Isolated import: clean src.* cache + insert human-handoff's own src parent directory
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_HH = _ROOT / "capabilities" / "human-handoff"

for _name in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
    del sys.modules[_name]
sys.path[:] = [p for p in sys.path if "/capabilities/" not in p]
sys.path.insert(0, str(_HH))

# Import directly from core.models module to bypass the circular dependency in src/core/__init__.py
# (src/core/__init__.py imports service.py, which in turn depends on ports.handoff_client)
import importlib  # noqa: E402

_models = importlib.import_module("src.core.models")
TicketStatusEnum = _models.TicketStatusEnum

from src.adapters.local_queue import LocalQueueHandoffClient  # noqa: E402
from src.adapters.mock import MockHandoffClient  # noqa: E402
# Pre-import default_rest (HH version) and pin the reference at module scope
# to avoid ``src`` being replaced by KB namespace when test_kb_ports runs later
from src.adapters import default_rest as _hh_default_rest  # noqa: E402

DefaultRestHandoffClient = _hh_default_rest.DefaultRestHandoffClient


class LocalQueueAdapterTests(unittest.TestCase):
    """Cover LocalQueueHandoffClient core behaviors."""

    def test_create_then_query_pending(self):
        c = LocalQueueHandoffClient(
            capacity=5, agent_pool_size=0, estimated_wait_per_slot=10
        )
        t = c.create_ticket(
            user_id="u1",
            subject="退款",
            description="3 天未到账",
            priority="normal",
            transcript=["用户：申请退款"],
        )
        # agent_pool_size=0 → no auto-connect; enters queue
        self.assertEqual(t.status, TicketStatusEnum.PENDING.value)
        self.assertEqual(t.queue_position, 1)
        self.assertEqual(t.eta_seconds, 10)

        status = c.query_status(t.ticket_id)
        self.assertIsNotNone(status)
        self.assertEqual(status.status, TicketStatusEnum.PENDING.value)

    def test_auto_connect_when_agent_available(self):
        c = LocalQueueHandoffClient(capacity=5, agent_pool_size=1)
        t = c.create_ticket(user_id="u_auto", subject="物流")
        self.assertEqual(t.status, TicketStatusEnum.PROCESSING.value)
        self.assertEqual(t.queue_position, 0)
        self.assertIsNotNone(t.agent_id)

    def test_cancel_releases_slot(self):
        c = LocalQueueHandoffClient(capacity=5, agent_pool_size=1)
        t = c.create_ticket(user_id="u_cancel", subject="发票")
        canceled = c.cancel_ticket(t.ticket_id, reason="用户主动取消")
        self.assertIsNotNone(canceled)
        self.assertEqual(canceled.status, TicketStatusEnum.CANCELED.value)
        # After cancel, status still queryable (closed ticket), but overall_status.connected = 0
        status = c.overall_status()
        self.assertEqual(status.connected, 0)

    def test_capacity_full_yields_timeout(self):
        c = LocalQueueHandoffClient(capacity=1, agent_pool_size=0)
        c.create_ticket(user_id="u_fill")
        t2 = c.create_ticket(user_id="u_overflow")
        self.assertEqual(t2.status, TicketStatusEnum.TIMEOUT.value)
        self.assertIsNotNone(t2.closed_at)

    def test_update_status_manual_close(self):
        c = LocalQueueHandoffClient(capacity=5, agent_pool_size=1)
        t = c.create_ticket(user_id="u_close")
        # auto-connected → close
        closed = c.update_status(t.ticket_id, "closed")
        self.assertEqual(closed.status, TicketStatusEnum.CLOSED.value)
        self.assertIsNotNone(closed.closed_at)
        self.assertEqual(c.overall_status().connected, 0)

    def test_get_or_attach_returns_active_only(self):
        c = LocalQueueHandoffClient(capacity=5, agent_pool_size=0)
        t = c.create_ticket(user_id="u_query")
        same = c.get_or_attach("u_query")
        self.assertEqual(same.ticket_id, t.ticket_id)
        # After cancel, get_or_attach should return None (only returns active tickets)
        c.cancel_ticket(t.ticket_id)
        self.assertIsNone(c.get_or_attach("u_query"))


class MockAdapterTests(unittest.TestCase):
    """MockHandoffClient demo data should be pre-populated."""

    def test_seed_three_tickets(self):
        c = MockHandoffClient(seed_demo_data=True, agent_pool_size=2)
        tickets = c.list_tickets(limit=10)
        ids = {t.ticket_id for t in tickets}
        # All three demo tickets present
        self.assertIn("demo_pending_001", ids)
        self.assertIn("demo_processing_001", ids)
        self.assertIn("demo_closed_001", ids)
        statuses = {t.status for t in tickets}
        self.assertIn(TicketStatusEnum.PENDING.value, statuses)
        self.assertIn(TicketStatusEnum.PROCESSING.value, statuses)
        self.assertIn(TicketStatusEnum.CLOSED.value, statuses)

    def test_seed_can_be_disabled(self):
        c = MockHandoffClient(seed_demo_data=False, agent_pool_size=2)
        self.assertEqual(c.list_tickets(), [])

    def test_inherits_create_behavior(self):
        c = MockHandoffClient(seed_demo_data=False, agent_pool_size=2)
        t = c.create_ticket(user_id="u_new", subject="测试")
        # agent_pool_size=2 → immediate connect
        self.assertEqual(t.status, TicketStatusEnum.PROCESSING.value)


class DefaultRestAdapterSecurityTests(unittest.TestCase):
    """DefaultRestHandoffClient base_url security validation (no actual HTTP calls)."""

    def test_https_public_allowed(self):
        # No real HTTP: constructing the object is enough to trigger _validate_base_url
        c = DefaultRestHandoffClient(base_url="https://crm.example.com")
        # Verify the validated url via _base
        self.assertTrue(c._base.startswith("https://"))

    def test_localhost_http_allowed(self):
        c = DefaultRestHandoffClient(base_url="http://localhost:8080")
        self.assertIn("localhost", c._base)

    def test_private_network_denied(self):
        for url in (
            "https://10.1.2.3",
            "https://192.168.0.1",
            "https://172.16.0.5",
            "https://9.0.0.1",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    DefaultRestHandoffClient(base_url=url)

    def test_non_https_remote_denied(self):
        with self.assertRaises(ValueError):
            DefaultRestHandoffClient(base_url="http://crm.example.com")

    def test_create_ticket_calls_post(self):
        """Simulate a successful create_ticket via requests, verify key payload fields."""
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "ticket_id": "T-9001",
            "queue_position": 2,
            "eta_seconds": 60,
        }

        c = DefaultRestHandoffClient(base_url="https://crm.example.com", token="tok")
        with patch.object(c._session, "post", return_value=fake_resp) as p:
            t = c.create_ticket(
                user_id="u9", subject="退款", description="3 天未到账"
            )
        self.assertEqual(t.ticket_id, "T-9001")
        self.assertEqual(t.queue_position, 2)
        # Verify call arguments
        self.assertEqual(p.call_count, 1)
        _, kwargs = p.call_args
        self.assertEqual(kwargs["json"]["user_id"], "u9")
        # Authorization header should carry Bearer
        self.assertIn("Bearer ", kwargs["headers"]["Authorization"])


if __name__ == "__main__":
    unittest.main()
