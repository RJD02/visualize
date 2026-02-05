"""MCP package for tool discovery and execution.

This local package provides minimal shims so installed libraries that import
`mcp` (e.g., google genai/adk) don't fail when the project also contains a
local `src/mcp` package. For full MCP support, replace these shims with the
real implementations or install the upstream `mcp` package in the environment.
"""

from .types import *  # re-export compatibility types
from .client.session import ClientSession
from .client.stdio import StdioServerParameters

# Export known shim names
__all__ = ["ClientSession", "StdioServerParameters", "Tool", "ToolResult", "ToolSpec"]
