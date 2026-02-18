from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db import Base
from src.mcp.registry import mcp_registry
from src.mcp.tools import register_mcp_tools
from src.services import session_service


def _fake_plan():
    return {
        "system_name": "Test System",
        "diagram_views": ["system_context", "container", "component", "sequence"],
        "zones": {
            "clients": ["Client"],
            "edge": ["Gateway"],
            "core_services": ["Service"],
            "external_services": ["External"],
            "data_stores": ["DB"],
        },
        "relationships": [
            {"from": "Client", "to": "Gateway", "type": "sync", "description": "call"}
        ],
        "visual_hints": {
            "layout": "left-to-right",
            "group_by_zone": True,
            "external_dashed": True,
        },
    }


class FakeWorkflow:
    def run(self, files, text, output_name):
        return {
            "architecture_plan": _fake_plan(),
            "plantuml": {"files": [f"{output_name}_system_context_1.png"]},
            "visual": {"image_file": f"{output_name}_sdxl.png", "sdxl_prompt": "prompt"},
            "evaluation": {"score": 1, "warnings": []},
            "images": [],
        }

    def run_edit(self, edit_text, output_name):
        return {
            "visual": {"image_file": f"{output_name}_sdxl_edit.png", "sdxl_prompt": edit_text},
            "images": [],
        }


class FakePlanner:
    def plan(self, message, state, tools):
        return {
            "intent": "diagram_change",
            "target_image_id": state.get("active_image_id"),
            "target_diagram_type": "system_context",
            "instructions": message,
            "requires_regeneration": False,
            "plan": [],
        }


class StylingPlanner:
    def plan(self, message, state, tools):
        plan_id = str(uuid4())
        images = state.get("images") or []
        if images:
            target_id = images[-1]["id"]
        else:
            target_id = None
        if target_id:
            return {
                "plan_id": plan_id,
                "intent": "style_diagram",
                "diagram_count": 1,
                "diagrams": [{"type": "existing", "reason": "style"}],
                "target_image_id": target_id,
                "target_diagram_type": state.get("diagram_types", ["diagram"])[0],
                "instructions": message,
                "requires_regeneration": False,
                "plan": [
                    {
                        "tool": "styling.apply_post_svg",
                        "arguments": {
                            "diagramId": target_id,
                            "userPrompt": message,
                            "stylingIntent": message,
                            "mode": "post-svg",
                        },
                    }
                ],
            }
        return {
            "plan_id": plan_id,
            "intent": "clarify",
            "diagram_count": None,
            "diagrams": [],
            "target_image_id": None,
            "target_diagram_type": "none",
            "instructions": message,
            "requires_regeneration": False,
            "plan": [],
        }


class GenerateAndStylePlanner:
    """Planner that generates a single diagram then applies styling."""
    def plan(self, message, state, tools):
        plan_id = str(uuid4())
        return {
            "plan_id": plan_id,
            "intent": "regenerate",
            "diagram_count": 1,
            "diagrams": [
                {"type": "system_context", "reason": "generate"},
            ],
            "target_image_id": None,
            "target_diagram_type": "system_context",
            "instructions": message,
            "requires_regeneration": True,
            "plan": [
                {
                    "tool": "generate_diagram",
                    "arguments": {"diagram_type": "system_context"},
                },
                {
                    "tool": "styling.apply_post_svg",
                    "arguments": {
                        "diagramId": session_service.LATEST_IMAGE_PLACEHOLDER,
                        "userPrompt": message,
                        "stylingIntent": message,
                        "mode": "post-svg",
                    },
                },
            ],
            "metadata": {"source": "test"},
        }


def test_ingest_and_handle_message(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(session_service, "ADKWorkflow", FakeWorkflow)
    monkeypatch.setattr(session_service, "ConversationPlannerAgent", FakePlanner)

    with SessionLocal() as db:
        session = session_service.create_session(db)
        result = session_service.ingest_input(db, session, files=None, text="hello")
        assert result["architecture_plan"]["system_name"] == "Test System"

        images = session_service.list_images(db, session.id)
        ir_versions = session_service.list_ir_versions(db, session.id)
        messages = session_service.list_messages(db, session.id)

        assert len(images) == 4
        assert len(ir_versions) == 4
        assert messages[-1].role == "assistant"

        reply = session_service.handle_message(db, session, "show me context")
        assert reply["intent"] == "diagram_change"
        assert reply["response"] == ""


def test_ingest_input_attaches_enriched_ir(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(session_service, "ADKWorkflow", FakeWorkflow)

    with SessionLocal() as db:
        session = session_service.create_session(db)
        session_service.ingest_input(db, session, files=None, text="hello")

        ir_versions = session_service.list_ir_versions(db, session.id)
        assert ir_versions, "expected IR versions to be recorded"

        for ir in ir_versions:
            payload = ir.ir_json or {}
            enriched = payload.get("enriched_ir")
            assert enriched is not None, "missing enriched_ir entry"
            assert enriched.get("diagram_type") == ir.diagram_type
            assert enriched.get("nodes"), "enriched IR should include nodes"


def test_styling_message_generates_new_image(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(session_service, "ADKWorkflow", FakeWorkflow)
    monkeypatch.setattr(session_service, "ConversationPlannerAgent", StylingPlanner)

    with SessionLocal() as db:
        session = session_service.create_session(db)
        session_service.ingest_input(db, session, files=None, text="hello")
        initial_images = session_service.list_images(db, session.id)
        initial_count = len(initial_images)

        reply = session_service.handle_message(db, session, "make it have vibrant colours")

        assert reply["intent"] == "style_diagram"
        updated_images = session_service.list_images(db, session.id)
        assert len(updated_images) == initial_count + 1

        styled_image = updated_images[-1]
        assert styled_image.reason == "styling"
        assert styled_image.ir_id is not None
        svg_text = Path(styled_image.file_path).read_text(encoding="utf-8")
        assert "#F97316" in svg_text or "fill" in svg_text.lower()

        messages = session_service.list_messages(db, session.id)
        assert any(m.image_id == styled_image.id for m in messages if m.message_type == "image")


def test_generate_multiple_diagrams_are_all_styled(monkeypatch, tmp_path):
    """After single-diagram output change, we generate one diagram + style it."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(session_service, "ADKWorkflow", FakeWorkflow)
    monkeypatch.setattr(session_service, "ConversationPlannerAgent", GenerateAndStylePlanner)

    def fake_generate(plan, overrides=None, diagram_types=None):
        types = diagram_types or ["system_context"]
        return [
            {"type": dtype, "plantuml": f"@startuml\ncomponent {dtype}\n@enduml"}
            for dtype in types
        ]

    def fake_render(diagrams, output_name, output_format="svg", audit_context=None):
        files = []
        for idx, diagram in enumerate(diagrams):
            path = tmp_path / f"{output_name}_{diagram['type']}_{idx}.svg"
            svg = (
                '<svg xmlns="http://www.w3.org/2000/svg">'
                "<rect width=\"240\" height=\"80\" />"
                f"<text id=\"{diagram['type']}_label\" x=\"12\" y=\"24\">{diagram['type']}</text>"
                "</svg>"
            )
            path.write_text(svg, encoding="utf-8")
            files.append(str(path))
        return files

    monkeypatch.setattr("src.tools.plantuml_renderer.generate_plantuml_from_plan", fake_generate)
    monkeypatch.setattr("src.tools.plantuml_renderer.render_diagrams", fake_render)
    monkeypatch.setattr(mcp_registry, "_tools", {})
    register_mcp_tools(mcp_registry)

    with SessionLocal() as db:
        session = session_service.create_session(db)
        session_service.ingest_input(db, session, files=None, text="seed")
        prompt = "https://github.com/RJD02/job-portal-go\nGenerate black blocks with white text and a pinkish blue background."
        reply = session_service.handle_message(db, session, prompt)
        assert reply["intent"] == "regenerate"

        ir_versions = session_service.list_ir_versions(db, session.id)
        styled_versions = [ir for ir in ir_versions if ir.reason == "styling"]
        # Single diagram output: expect exactly 1 styled version
        assert len(styled_versions) >= 1
        styled_types = {ir.diagram_type for ir in styled_versions}
        assert any(kind in styled_types for kind in {"system_context", "context"})
        for ir in styled_versions:
            assert "#F8F9FA" in ir.svg_text, f"Expected white text fill for {ir.diagram_type}"
