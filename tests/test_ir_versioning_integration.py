from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db import Base
from src.services import session_service
from src.mcp.registry import mcp_registry
from src.mcp.tools import register_mcp_tools


def _plan():
    return {
        "system_name": "Test System",
        "diagram_views": ["system_context", "container"],
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
            "layout": "top-down",
            "group_by_zone": True,
            "external_dashed": True,
        },
    }


class FakeWorkflow:
    def run(self, files, text, output_name):
        return {
            "architecture_plan": _plan(),
            "plantuml": {"files": []},
            "visual": {},
            "evaluation": {"score": 1, "warnings": []},
            "images": [],
        }

    def run_edit(self, edit_text, output_name):
        return {
            "visual": {},
            "images": [],
        }


class PlannerEditIR:
    def plan(self, message, state, tools):
        return {
            "intent": "edit_image",
            "diagram_count": None,
            "diagrams": [],
            "target_image_id": state.get("active_image_id"),
            "target_diagram_type": "system_context",
            "instructions": message,
            "requires_regeneration": False,
            "plan": [
                {"tool": "edit_diagram_ir", "arguments": {"instruction": message}},
            ],
        }


def test_ir_versioning_flow(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(session_service, "ADKWorkflow", FakeWorkflow)
    monkeypatch.setattr(session_service, "ConversationPlannerAgent", PlannerEditIR)

    register_mcp_tools(mcp_registry)

    with SessionLocal() as db:
        session = session_service.create_session(db)
        session_service.ingest_input(db, session, files=None, text="hello")

        ir_versions = session_service.list_ir_versions(db, session.id)
        assert len(ir_versions) == 2

        session_service.handle_message(db, session, "move core_services above edge")
        session_service.handle_message(db, session, "move clients below edge")

        ir_versions = session_service.list_ir_versions(db, session.id)
        assert len(ir_versions) == 4

        messages = session_service.list_messages(db, session.id)
        image_messages = [m for m in messages if getattr(m, "message_type", "") == "image"]
        assert len(image_messages) >= 3
        assert all((m.content or "") == "" for m in image_messages)
