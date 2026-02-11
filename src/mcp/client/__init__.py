"""Client subpackage shim for MCP compatibility."""

from .session import ClientSession
from .stdio import StdioServerParameters, stdio_client
from .sse import sse_client
from .streamable_http import streamable_http_client, create_mcp_http_client
from .http_client import MCPHTTPClient, discover_tools, execute_tool

__all__ = [
	"ClientSession",
	"StdioServerParameters",
	"stdio_client",
	"sse_client",
	"streamable_http_client",
	"create_mcp_http_client",
	"MCPHTTPClient",
	"discover_tools",
	"execute_tool",
]
