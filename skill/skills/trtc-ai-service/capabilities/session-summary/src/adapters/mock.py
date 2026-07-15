"""mock write-back sink — default implementation, no external dependencies, suitable for demos."""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict

from .base import SummarySink

logger = logging.getLogger(__name__)


class MockSink(SummarySink):
    name = "mock"

    def write(self, summary_record: Dict[str, Any]) -> Dict[str, Any]:
        sid = str(summary_record.get("session_id", ""))
        record_id = "CRM-MOCK-" + hashlib.md5(sid.encode("utf-8")).hexdigest()[:10].upper()
        topics = (summary_record.get("summary") or {}).get("topics") or []
        logger.info("[session-summary][mock] write-back session=%s topics=%s -> %s",
                    sid, topics[:3], record_id)
        return {"record_id": record_id, "accepted": True, "sink": self.name, "_mock": True}
