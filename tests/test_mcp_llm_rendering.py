from __future__ import annotations

from src.mcp import tools as mcp_tools

PLANTUML_TEXT = """@startuml
actor Client
component "API" as Api
Client --> Api
@enduml"""

MERMAID_TEXT = """graph LR
  A[Client] --> B[Service]
"""


def test_tool_generate_plantuml_prefers_llm(monkeypatch):
    captured: dict[str, object] = {}

    def fake_render_diagrams(diagrams, output_name, output_format="svg", audit_context=None):
        captured["diagrams"] = diagrams
        captured["audit_context"] = audit_context
        assert output_name == "llm_out"
        assert output_format == "svg"
        return ["/tmp/out.svg"]

    monkeypatch.setattr(mcp_tools, "render_diagrams", fake_render_diagrams)
    monkeypatch.setattr(mcp_tools, "read_text_file", lambda path: "<svg>component</svg>")

    context = {"plan_id": "plan-123", "session_id": "sess-1", "user_message": "prompt", "db": object()}
    result = mcp_tools.tool_generate_plantuml(
        context,
        None,
        "llm_out",
        llm_diagram=PLANTUML_TEXT,
        diagram_type="component",
        format="plantuml",
    )

    diagrams = captured["diagrams"]
    assert diagrams[0]["llm_diagram"].startswith("@startuml")
    assert diagrams[0]["format"] == "plantuml"
    assert result["files"] == ["/tmp/out.svg"]
    ir_entry = result["ir_entries"][0]
    assert ir_entry["diagram_type"] == "component"
    assert ir_entry["svg"] == "<svg>component</svg>"


def test_tool_generate_diagram_defaults_to_llm(monkeypatch):
    captured: dict[str, object] = {}

    class DummyPlanModel:
        @classmethod
        def parse_obj(cls, data):
            return object()

    def fake_generate(plan, overrides=None, diagram_types=None):
        captured["diagram_types"] = diagram_types
        return [
            {
                "type": (diagram_types or ["system_context"])[0],
                "llm_diagram": PLANTUML_TEXT,
                "format": "plantuml",
            }
        ]

    def fake_render(diagrams, output_name, output_format="svg", audit_context=None):
        captured["diagrams"] = diagrams
        assert output_name == "ctx_out"
        return ["/tmp/ctx.svg"]

    monkeypatch.setattr(mcp_tools, "ArchitecturePlan", DummyPlanModel)
    monkeypatch.setattr(mcp_tools, "generate_plantuml_from_plan", fake_generate)
    monkeypatch.setattr(mcp_tools, "render_diagrams", fake_render)
    monkeypatch.setattr(mcp_tools, "read_text_file", lambda path: "<svg ctx>")

    result = mcp_tools.tool_generate_diagram(
        {},
        {"diagram_views": ["system_context"]},
        "ctx_out",
        "system_context",
    )

    diagrams = captured["diagrams"]
    assert diagrams[0]["llm_diagram"].startswith("@startuml")
    assert captured["diagram_types"] == ["system_context"]
    assert result["ir_entries"][0]["svg"] == "<svg ctx>"


def test_tool_mermaid_renderer_prefers_llm(monkeypatch, tmp_path):
    svg_path = tmp_path / "diagram.svg"
    mmd_path = tmp_path / "diagram.mmd"
    svg_content = "<svg>mermaid</svg>"

    def fake_render_llm_mermaid(diagram_text: str, output_name: str):
        assert output_name == "merm_out"
        return {
            "file_path": str(svg_path),
            "source_path": str(mmd_path),
            "sanitized_text": diagram_text.strip(),
            "warnings": [],
            "svg_text": svg_content,
        }

    monkeypatch.setattr(mcp_tools, "render_llm_mermaid", fake_render_llm_mermaid)

    result = mcp_tools.tool_mermaid_renderer(
        {},
        ir=None,
        diagram_text=MERMAID_TEXT,
        output_name="merm_out",
    )

    assert result["svg"] == svg_content
    assert result["file_path"] == str(svg_path)
    assert result["source_path"] == str(mmd_path)
    assert result["warnings"] == []
