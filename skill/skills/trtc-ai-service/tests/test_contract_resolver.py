"""Phase 3 阶段 6：scripts/lib/contract_resolver.py 单元测试。

覆盖目标：
- load_business_contract：能加载 human-handoff / knowledge-base 两个能力包并通过 BC001~BC006 校验
- diff_contracts：同名同类型 → 无 diff（L1）；rename 候选命中同义词字典；类型不兼容 → L2
- decide_level：protocol 级别 method/body 不一致 → L3；out-of-slot rename → L2；slot 内 rename → L1
- validate_manifest：能产出（或不产出）warning 列表
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.lib.contract_resolver import (  # noqa: E402
    BusinessContract,
    ContractError,
    DegradeLevel,
    decide_level,
    diff_contracts,
    load_business_contract,
    validate_manifest,
)
from scripts.lib.curl_parser import AuthSpec, ParsedApi  # noqa: E402


_HH_DIR = _ROOT / "capabilities" / "human-handoff"
_KB_DIR = _ROOT / "capabilities" / "knowledge-base"


class LoadBusinessContractTests(unittest.TestCase):
    """Read real manifests and verify correct field parsing."""

    def test_load_human_handoff_outbound_apis(self):
        bc = load_business_contract(_HH_DIR)
        self.assertEqual(bc.capability, "human-handoff")
        self.assertTrue(bc.port_class.endswith("HandoffClient"))
        outs = bc.outbound_apis()
        names = {a.name for a in outs}
        # At least three outbound ticket APIs
        self.assertIn("ticket.create", names)
        self.assertIn("ticket.status_query", names)
        self.assertIn("ticket.cancel", names)
        # Inbound APIs should not mix into outbound
        for a in outs:
            self.assertEqual(a.direction, "outbound")

    def test_load_knowledge_base_outbound_apis(self):
        bc = load_business_contract(_KB_DIR)
        self.assertEqual(bc.capability, "knowledge-base")
        names = {a.name for a in bc.outbound_apis()}
        # At least faq.search
        self.assertIn("faq.search", names)

    def test_get_api_lookup(self):
        bc = load_business_contract(_HH_DIR)
        api = bc.get_api("ticket.create")
        self.assertIsNotNone(api)
        self.assertEqual(api.method, "POST")
        self.assertIn("user_id", api.request_schema)
        self.assertIn("response.ticket_id", api.adapter_slots)

    def test_load_missing_manifest_raises(self):
        with self.assertRaises(ContractError) as ctx:
            load_business_contract(_ROOT / "no_such_capability_dir")
        self.assertEqual(ctx.exception.code, "BC000")

    def test_validate_manifest_runs(self):
        # validate_manifest must not raise fatal; BC004 warnings are allowed (array-type slot paths may hit hits[])
        warnings_hh = validate_manifest(_HH_DIR)
        self.assertIsInstance(warnings_hh, list)
        warnings_kb = validate_manifest(_KB_DIR)
        self.assertIsInstance(warnings_kb, list)
        # Warning strings should start with BC prefix
        for w in warnings_hh + warnings_kb:
            self.assertTrue(w.startswith("BC"), w)


class DiffContractsTests(unittest.TestCase):
    """构造默认契约 + 用户 ParsedApi，验证 diff / level 决策。"""

    def setUp(self):
        bc = load_business_contract(_HH_DIR)
        self.api = bc.get_api("ticket.create")
        self.assertIsNotNone(self.api)

    def _make_user(
        self,
        *,
        method="POST",
        path="/tickets",
        request_schema=None,
        body_format="json",
    ):
        return ParsedApi(
            method=method,
            base_url="https://crm.example.com",
            path=path,
            headers={},
            auth=AuthSpec(type="bearer", location="header", name="Authorization"),
            request_schema=request_schema or {},
            response_schema={},
            body_format=body_format,
            source="curl",
        )

    def test_l1_when_same_field_names(self):
        """Same field names + same types + method/path match → L1."""
        user = self._make_user(
            request_schema={
                "user_id": "string",
                "subject": "string",
                "description": "string",
                "priority": "string",
                "transcript": "string[]",
            }
        )
        diff = diff_contracts(self.api, user)
        self.assertFalse(diff.protocol_mismatch)
        self.assertEqual(decide_level(diff), DegradeLevel.L1)

    def test_l1_when_slot_rename(self):
        """subject → title (synonym, inside adapter_slots) → still L1."""
        user = self._make_user(
            request_schema={
                "user_id": "string",
                "title": "string",         # subject → title（slot 内）
                "description": "string",
                "priority": "string",      # priority 仍同名
                "transcript": "string[]",
            }
        )
        diff = diff_contracts(self.api, user)
        self.assertEqual(decide_level(diff), DegradeLevel.L1)
        # Must have a rename record (subject → title) that is in-slot
        renames = [f for f in diff.fields if f.kind == "rename"]
        self.assertTrue(any(f.in_slot and "subject" in f.path for f in renames))

    def test_l2_when_out_of_slot_rename(self):
        """user_id → customer_id (synonym, but user_id not in adapter_slots) → L2."""
        user = self._make_user(
            request_schema={
                "customer_id": "string",   # user_id 重命名（不在 slot）
                "subject": "string",
                "description": "string",
                "priority": "string",
                "transcript": "string[]",
            }
        )
        diff = diff_contracts(self.api, user)
        self.assertEqual(decide_level(diff), DegradeLevel.L2)

    def test_l3_when_method_mismatch(self):
        """方法不一致（POST → PUT）→ protocol_mismatch → L3。"""
        user = self._make_user(method="PUT")
        diff = diff_contracts(self.api, user)
        self.assertTrue(diff.protocol_mismatch)
        self.assertEqual(decide_level(diff), DegradeLevel.L3)

    def test_l3_when_raw_body_format(self):
        """body_format=raw (non-JSON) → protocol_mismatch → L3."""
        user = self._make_user(body_format="raw")
        diff = diff_contracts(self.api, user)
        self.assertTrue(diff.protocol_mismatch)
        self.assertEqual(decide_level(diff), DegradeLevel.L3)

    def test_response_missing_does_not_block_l1(self):
        """User did not provide response → not counted as a protocol/L2/L3 obstacle."""
        user = self._make_user(
            request_schema={
                "user_id": "string",
                "subject": "string",
                "description": "string",
                "priority": "string",
                "transcript": "string[]",
            }
        )
        # response 留空
        diff = diff_contracts(self.api, user)
        self.assertEqual(decide_level(diff), DegradeLevel.L1)
        # 但应有 user_response_missing 记录
        kinds = {f.kind for f in diff.fields}
        self.assertIn("user_response_missing", kinds)


if __name__ == "__main__":
    unittest.main()
