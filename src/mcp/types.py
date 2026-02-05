"""Compatibility shim for `mcp.types` imports.

This project provides a minimal local `mcp` package; some installed libraries
expect `mcp.types` to exist. Provide lightweight placeholders to avoid
ImportError during runtime. If fuller compatibility is needed, replace these
with concrete implementations.
"""
from typing import Any

__all__ = ["Tool", "ToolResult", "ToolSpec"]


class ToolSpec:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass


class Tool:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass


class ToolResult:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass
