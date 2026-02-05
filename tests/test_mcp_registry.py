from src.mcp.registry import MCPRegistry, MCPTool


def test_registry_register_and_execute():
    registry = MCPRegistry()

    def handler(context, name: str):
        return {"message": f"hi {name}"}

    tool = MCPTool(
        name="greet",
        description="Test tool",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"message": {"type": "string"}}},
        side_effects="none",
        handler=handler,
    )

    registry.register(tool)
    tools = registry.list_tools()
    assert tools and tools[0]["name"] == "greet"

    result = registry.execute("greet", {"name": "neo"}, context={})
    assert result["message"] == "hi neo"


def test_registry_unknown_tool_raises():
    registry = MCPRegistry()
    try:
        registry.execute("missing", {}, context={})
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Unknown tool" in str(exc)
