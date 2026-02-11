"""In-process MCP registry for tool discovery and execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    side_effects: str
    handler: Callable[..., Dict[str, Any]]
    tool_id: Optional[str] = None
    version: Optional[str] = None
    mode: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def identifier(self) -> str:
        return self.tool_id or self.name


class MCPRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, MCPTool] = {}

    def register(self, tool: MCPTool) -> None:
        self._tools[tool.identifier] = tool

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": tool.identifier,
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
                "side_effects": tool.side_effects,
                "mode": tool.mode,
                "version": tool.version,
                "metadata": tool.metadata or {},
            }
            for tool in self._tools.values()
        ]

    def get_tool(self, tool_id: str) -> Optional[MCPTool]:
        return self._tools.get(tool_id)

    def execute(self, tool_id: str, args: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        tool = self.get_tool(tool_id)
        if not tool:
            raise ValueError(f"Unknown tool: {tool_id}")
        return tool.handler(context=context, **args)


mcp_registry = MCPRegistry()
