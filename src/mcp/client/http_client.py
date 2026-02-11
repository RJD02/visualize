"""Minimal HTTP client for MCP discovery and execution."""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


class MCPHTTPClient:
    """Convenience wrapper around the MCP HTTP adapter endpoints."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def discover(self) -> Dict[str, Any]:
        response = self._client.get(f"{self._base_url}/mcp/discover")
        response.raise_for_status()
        return response.json()

    def execute(
        self,
        tool_id: str,
        args: Optional[Dict[str, Any]] = None,
        *,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"tool_id": tool_id, "args": args or {}}
        if session_id:
            payload["session_id"] = session_id
        response = self._client.post(f"{self._base_url}/mcp/execute", json=payload)
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MCPHTTPClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()


def discover_tools(base_url: str, timeout: float = 30.0) -> Dict[str, Any]:
    with MCPHTTPClient(base_url, timeout=timeout) as client:
        return client.discover()


def execute_tool(
    base_url: str,
    tool_id: str,
    args: Optional[Dict[str, Any]] = None,
    *,
    session_id: Optional[str] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    with MCPHTTPClient(base_url, timeout=timeout) as client:
        return client.execute(tool_id, args=args, session_id=session_id)
