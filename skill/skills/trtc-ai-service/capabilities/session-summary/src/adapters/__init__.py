"""session-summary write-back adapter layer."""
from .base import SummarySink
from .factory import get_sink

__all__ = ["SummarySink", "get_sink"]
