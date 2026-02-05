"""Minimal streamable_http shim."""
from __future__ import annotations

from typing import Any, Protocol

MCP_PROTOCOL_VERSION = "1"


def streamable_http_client(*args: Any, **kwargs: Any) -> None:
    return None


def create_mcp_http_client(*args: Any, **kwargs: Any) -> None:
    return None


def streamablehttp_client(*args: Any, **kwargs: Any) -> None:
    return None


class McpHttpClientFactory(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - protocol shim
        ...

