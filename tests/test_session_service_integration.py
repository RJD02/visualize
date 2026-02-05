from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db import Base
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
