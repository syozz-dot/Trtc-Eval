"""Shim package: re-exports shared TRTC CLI tools from sibling ``skills/trtc/tools/``.

Allows ``python3 -m tools.kb`` (and other ``tools.*``) to work when the shell cwd
is ``skills/trtc-chat/``, not only ``skills/trtc/``.
"""
