"""session-summary write-back adapter layer.

Consistent "three-tier adapter + factory" paradigm matching knowledge-base / human-handoff:
    mock          — Default; summary only logged + returns mock record_id, no external system needed,
                    allows local / Path A demos to immediately see "write-back success".
    local_json    — Append to local JSONL (data/_writeback.jsonl), can be checked offline.
    default_rest  — POST to user's real CRM / ticketing system (SS_REST_BASE_URL).

External contract see manifest.business_contract.external_apis[summary.write_to_crm].
When interface fields don't align, refer to INTERFACE_ADAPT.md for request/response mapping.
"""
from __future__ import annotations

import abc
from typing import Any, Dict


class SummarySink(abc.ABC):
    """Unified abstraction for session summary write-back targets."""

    name: str = "base"

    @abc.abstractmethod
    def write(self, summary_record: Dict[str, Any]) -> Dict[str, Any]:
        """Write a finalized summary record to the target system.

        Returns
        -------
        dict: {"record_id": str, "accepted": bool, "sink": str}
        """
        raise NotImplementedError
