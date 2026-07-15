"""knowledge-base capability: FAQ retrieval + keyword matching.

Minimal implementation:
- Data source: local JSON file (hot-reloadable)
- Matching: keyword weighted scoring + optional TF-IDF (stop-word filtering)
- Zero external dependencies, pure Python implementation
"""
__version__ = "1.0.0"
