"""tool-calling built-in "Generic AI Customer Service Tool Set" (alpha-track default = local mock).

Design principles (aligned with SKILL §6 point 2):
- Industry-neutral: not tied to specific verticals; covers common actions across most customer service scenarios
  (check document status / check business info / make appointment / submit feedback).
- Works out of the box: each tool has a directly runnable alpha-track mock implementation;
  users on Path A or local demos can see the capability in effect immediately, even without a real backend API.
- Smoothly replaceable: each tool also declares a beta-track (remote HTTPS) placeholder in data/tools.yaml;
  connecting to a real system only requires pointing the beta endpoint to your own API (or adapting per INTERFACE_ADAPT.md).

Return value must be JSON-serializable; mock data uniformly carries "_mock": true marker,
making it easy for frontend / logs to distinguish "demo data" from "real business data".
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict


def _stable_pick(seed: str, choices):
    """Stably select a value based on seed (same input always returns the same result, making demos reproducible)."""
    h = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16)
    return choices[h % len(choices)]


def query_order_status(order_id: str = "", **_: Any) -> Dict[str, Any]:
    """Query document / order / ticket status (generic customer service action).

    Parameters:
        order_id: Document number (order number / ticket number / appointment number fine).
    """
    if not order_id:
        return {"_mock": True, "error": "order_id is required"}
    status = _stable_pick(order_id, ["processing", "confirmed", "in_progress", "completed", "cancelled"])
    return {
        "_mock": True,
        "order_id": order_id,
        "status": status,
        "updated_at": int(time.time()),
        "note": "Demo data from built-in mock tool; point the β endpoint to your real system to use live data.",
    }


def get_business_info(topic: str = "hours", **_: Any) -> Dict[str, Any]:
    """Query business info (hours / address / contact etc.), common high-frequency customer service question.

    Parameters:
        topic: hours | address | contact | all
    """
    info = {
        "hours": "Mon-Sun 10:00-22:00 (last entry 21:00)",
        "address": "No.1 Demo Street, Example District",
        "contact": "+86-000-0000-0000 / support@example.com",
    }
    topic = (topic or "hours").lower()
    data = info if topic == "all" else {topic: info.get(topic, info["hours"])}
    return {"_mock": True, "topic": topic, **data,
            "note": "Demo data from built-in mock tool; replace with your real business profile."}


def book_appointment(date: str = "", time_slot: str = "", party_size: int = 2, **_: Any) -> Dict[str, Any]:
    """Create reservation / booking (restaurant reservation, service appointment, callback booking etc. generic actions).

    Parameters:
        date: Date, e.g. 2026-06-12
        time_slot: Time slot, e.g. 18:30
        party_size: Party size / quantity
    """
    if not date or not time_slot:
        return {"_mock": True, "error": "date and time_slot are required"}
    confirm = "BK" + hashlib.md5(f"{date}{time_slot}{party_size}".encode()).hexdigest()[:8].upper()
    return {
        "_mock": True,
        "confirmation_id": confirm,
        "date": date,
        "time_slot": time_slot,
        "party_size": int(party_size) if str(party_size).isdigit() else party_size,
        "status": "confirmed",
        "note": "Demo booking created by built-in mock tool; wire the β endpoint to your reservation system.",
    }


def submit_feedback(rating: int = 5, comment: str = "", **_: Any) -> Dict[str, Any]:
    """Submit satisfaction / feedback (common end-of-session action).

    Parameters:
        rating: 1-5 rating
        comment: Text feedback (optional)
    """
    try:
        rating = max(1, min(5, int(rating)))
    except (TypeError, ValueError):
        rating = 5
    return {
        "_mock": True,
        "received": True,
        "rating": rating,
        "comment": (comment or "")[:512],
        "note": "Demo acknowledgement from built-in mock tool.",
    }
