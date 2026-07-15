"""knowledge-base core module."""
from .models import FaqEntry, KbStats, SearchHit
from .service import KbService, get_default_service, reset_default_service

__all__ = [
    "FaqEntry",
    "KbService",
    "KbStats",
    "SearchHit",
    "get_default_service",
    "reset_default_service",
]
