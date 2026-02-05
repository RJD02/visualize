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
            "plantuml": {"files": [f"{output_name}_context_1.png"]},
            "visual": {"image_file": f"{output_name}_sdxl.png", "sdxl_prompt": "prompt"},
            "evaluation": {"score": 1, "warnings": []},
            "images": [],
        }

    def run_edit(self, edit_text, output_name):
        return {
            "visual": {"image_file": f"{output_name}_sdxl_edit.png", "sdxl_prompt": edit_text},
            "images": [],
        }


class PlannerDiagramChange:
    def plan(self, message, state, tools):
        return {
            "intent": "diagram_change",
            "target_image_id": state.get("active_image_id"),
            "target_diagram_type": "system_context",
            "instructions": message,
            "requires_regeneration": False,
            "plan": [],
        }


class PlannerExplain:
    def plan(self, message, state, tools):
        return {
            "intent": "explain",
            "target_image_id": None,
            "target_diagram_type": "none",
            "instructions": message,
            "requires_regeneration": False,
            "plan": [],
        }


def test_diagram_change_creates_new_image_and_parent(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(session_service, "ADKWorkflow", FakeWorkflow)
    monkeypatch.setattr(session_service, "ConversationPlannerAgent", PlannerDiagramChange)

    with SessionLocal() as db:
        session = session_service.create_session(db)
        session_service.ingest_input(db, session, files=None, text="hello")
        images_before = session_service.list_images(db, session.id)
        assert len(images_before) == 4

        reply = session_service.handle_message(db, session, "convert to context")
        assert reply["intent"] == "diagram_change"

        images_after = session_service.list_images(db, session.id)
        assert len(images_after) == 5
        assert images_after[-1].parent_image_id == images_before[-1].id

        messages = session_service.list_messages(db, session.id)
        assert messages[-1].image_id == images_after[-1].id


def test_explain_does_not_create_image(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(session_service, "ADKWorkflow", FakeWorkflow)
    monkeypatch.setattr(session_service, "ConversationPlannerAgent", PlannerExplain)
    monkeypatch.setattr(session_service, "explain_architecture", lambda plan, msg: "ok")

    with SessionLocal() as db:
        session = session_service.create_session(db)
        session_service.ingest_input(db, session, files=None, text="hello")
        count_before = len(session_service.list_images(db, session.id))

        reply = session_service.handle_message(db, session, "explain")
        assert reply["intent"] == "explain"

        count_after = len(session_service.list_images(db, session.id))
        assert count_after == count_before
