"""tool-calling capability: alpha/beta dual-track tool calling.

Core modules:
- registry  Load tools from YAML registration declarations + Python entry points
- dispatcher  Recognize and trigger calls from conversation text ("/tool name {json}")
- router  REST endpoints
"""
__version__ = "1.0.0"
