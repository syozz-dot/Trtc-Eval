"""conversation-core: Voice Agent generic skeleton.

This package implements the pipeline orchestration for ASR / LLM / TTS / session management only,
with no built-in industry knowledge bases, FAQ templates, or business rules.
All business capabilities are overlaid via external standalone capability packages
using manifest.yaml injection points.
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
