"""In-process MCP registry for tool discovery and execution."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    side_effects: str
    handler: Callable[..., Dict[str, Any]]


class MCPRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, MCPTool] = {}

    def register(self, tool: MCPTool) -> None:
        self._tools[tool.name] = tool

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
                "side_effects": tool.side_effects,
            }
            for tool in self._tools.values()
        ]

    def get_tool(self, name: str) -> Optional[MCPTool]:
        return self._tools.get(name)

    def execute(self, name: str, args: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")
        return tool.handler(context=context, **args)


mcp_registry = MCPRegistry()
