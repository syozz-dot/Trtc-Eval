"""MockKbClient — mock implementation for Recipe demo recording.

Inherits LocalJsonKbClient; seeds embedded demo FAQ into memory on construction (no disk file dependency).

Applicable scenarios:
- User's first Recipe launch works out of the box even before data/faq.json has been filled in
- Stable data for video demos, won't break due to external file changes
"""
from __future__ import annotations

import os
from typing import List

from ..core.models import FaqEntry
from .local_json import LocalJsonKbClient


_DEMO_FAQ: List[dict] = [
    {
        "id": "demo_refund",
        "question": "How do I request a refund?",
        "answer": "Go to My Orders, pick the item, tap Request refund and fill in the reason. Once approved, the amount returns to your original payment within 1-3 business days.",
        "keywords": ["refund", "money back", "return", "cancel order"],
        "source": "demo_seed",
    },
    {
        "id": "demo_logistics",
        "question": "How long does shipping take?",
        "answer": "Standard items ship within 48 hours. Major cities receive in 3-5 days; remote areas 5-7 days. You can track shipments in real time under My Orders.",
        "keywords": ["shipping", "delivery", "tracking", "where is my package", "logistics"],
        "source": "demo_seed",
    },
    {
        "id": "demo_invoice",
        "question": "How can I get an invoice?",
        "answer": "Tick \"Need invoice\" at checkout and fill in your billing details. For existing orders, open the order in My Orders and tap Request invoice. E-invoices are emailed within 24 hours.",
        "keywords": ["invoice", "receipt", "billing", "tax"],
        "source": "demo_seed",
    },
    {
        "id": "demo_size",
        "question": "What if the size doesn't fit?",
        "answer": "We offer 7-day free size exchange — return shipping is on us. Open My Orders, tap Exchange size and follow the instructions. If your size is out of stock you can request a refund and re-order.",
        "keywords": ["size", "exchange", "doesn't fit", "wrong size"],
        "source": "demo_seed",
    },
    {
        "id": "demo_after_sale",
        "question": "What is the warranty period?",
        "answer": "All products carry a 1-year warranty. Electronics may be replaced within 30 days; after 30 days the manufacturer's warranty policy applies. Provide your order ID and a description of the issue and we'll open a ticket for you.",
        "keywords": ["warranty", "after-sale", "repair", "broken", "defective"],
        "source": "demo_seed",
    },
]


class MockKbClient(LocalJsonKbClient):
    """Mock implementation for demos."""

    is_mock = True

    def __init__(
        self,
        *,
        min_score: float = 0.05,    # More lenient threshold for demos
        top_k: int = 3,
        seed_demo_data: bool = True,
    ) -> None:
        # No data_file specified — data is entirely memory-resident
        super().__init__(
            data_file=None,
            min_score=min_score,
            top_k=top_k,
        )
        if seed_demo_data:
            self._seed()

    def _seed(self) -> None:
        for raw in _DEMO_FAQ:
            entry = FaqEntry.from_dict(raw)
            self._entries.append(entry)
        self._rebuild_df()


# ---------------------------------------------------------------------------
def from_env() -> MockKbClient:
    return MockKbClient(
        min_score=float(os.getenv("KB_MIN_SCORE", "0.05")),
        top_k=int(os.getenv("KB_TOP_K", "3")),
        seed_demo_data=os.getenv("KB_MOCK_SEED", "1") not in ("0", "false", "False"),
    )
