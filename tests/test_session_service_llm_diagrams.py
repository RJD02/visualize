from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.db import Base
from src.db_models import DiagramIR, StylingAudit
from src.services import session_service


PLANTUML_TEXT = """@startuml
actor Client
component "API Gateway" as Api
component "Service" as Service
Client --> Api : https
Api --> Service : grpc
@enduml"""


MERMAID_TEXT = """graph TD
  Client[Client App] --> Service[Core Service]
  Service --> DB[(Data Store)]
"""


class _RegistryStub:
    def get_tool(self, name: str) -> bool:
        return True

    def list_tools(self) -> list[str]:
        return []


def _init_db(db_file: Path):
    engine = create_engine(f"sqlite+pysqlite:///{db_file}", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, future=True, autoflush=False, autocommit=False)


def _mock_planner(plan_payload: dict):
    class _Planner:  # pragma: no cover - simple stub
        def plan(self, message, state, tools):
            return plan_payload

    return _Planner


def test_llm_plantuml_flow_records_audit(monkeypatch, tmp_path):
    session_factory = _init_db(tmp_path / "plantuml.db")
    monkeypatch.setattr(session_service, "mcp_registry", _RegistryStub())
    monkeypatch.setattr(session_service, "register_mcp_tools", lambda registry: None)

    plan_payload = {
        "plan_id": str(uuid4()),
        "intent": "diagram_change",
        "plan": [
            {
                "llm_diagram": PLANTUML_TEXT,
                "format": "plantuml",
                "diagram_type": "component",
            }
        ],
    }
    monkeypatch.setattr(session_service, "ConversationPlannerAgent", _mock_planner(plan_payload))

    def fake_render_llm_plantuml(diagram_text: str, output_name: str, diagram_type: str | None = None):
        svg_path = tmp_path / f"{output_name}.svg"
        svg_path.write_text("<svg><text>component</text></svg>", encoding="utf-8")
        return {
            "file_path": str(svg_path),
            "sanitized_text": diagram_text.strip(),
            "warnings": [],
        }

    monkeypatch.setattr(session_service, "render_llm_plantuml", fake_render_llm_plantuml)

    with session_factory() as db:
        session = session_service.create_session(db)
        reply = session_service.handle_message(db, session, "sync the component diagram")

        assert reply["tool_results"], "Expected llm.diagram tool result"
        tool_result = reply["tool_results"][0]
        assert tool_result["tool"] == "llm.diagram"
        assert "audit_id" in tool_result

        images = session_service.list_images(db, session.id)
        assert len(images) == 1
        assert images[0].reason == "llm diagram: component"

        audits = db.execute(select(StylingAudit)).scalars().all()
        assert len(audits) == 1
        audit = audits[0]
        assert audit.llm_format == "plantuml"
        assert audit.llm_diagram.strip().startswith("@startuml")
        assert audit.sanitized_diagram.strip().startswith("@startuml")
        assert audit.validation_warnings == []

        ir_versions = db.execute(select(DiagramIR)).scalars().all()
        assert len(ir_versions) == 1
        assert ir_versions[0].plantuml_text.strip().startswith("@startuml")


def test_llm_mermaid_flow_records_audit(monkeypatch, tmp_path):
    session_factory = _init_db(tmp_path / "mermaid.db")
    monkeypatch.setattr(session_service, "mcp_registry", _RegistryStub())
    monkeypatch.setattr(session_service, "register_mcp_tools", lambda registry: None)

    plan_payload = {
        "plan_id": str(uuid4()),
        "intent": "diagram_change",
        "plan": [
            {
                "llm_diagram": MERMAID_TEXT,
                "format": "mermaid",
                "diagram_type": "system_context",
            }
        ],
    }
    monkeypatch.setattr(session_service, "ConversationPlannerAgent", _mock_planner(plan_payload))

    def fake_render_llm_mermaid(diagram_text: str, output_name: str):
        svg_path = tmp_path / f"{output_name}.svg"
        svg_content = "<svg><text>system</text></svg>"
        svg_path.write_text(svg_content, encoding="utf-8")
        return {
            "file_path": str(svg_path),
            "svg_text": svg_content,
            "sanitized_text": diagram_text.strip(),
            "warnings": ["trimmed whitespace"],
        }

    monkeypatch.setattr(session_service, "render_llm_mermaid", fake_render_llm_mermaid)

    with session_factory() as db:
        session = session_service.create_session(db)
        reply = session_service.handle_message(db, session, "need a system view")

        assert reply["tool_results"], "Expected llm.diagram tool result"
        tool_result = reply["tool_results"][0]
        assert tool_result["tool"] == "llm.diagram"

        images = session_service.list_images(db, session.id)
        assert len(images) == 1
        assert images[0].reason == "llm diagram: system_context"

        audits = db.execute(select(StylingAudit)).scalars().all()
        assert len(audits) == 1
        audit = audits[0]
        assert audit.llm_format == "mermaid"
        assert audit.sanitized_diagram.strip().startswith("graph TD")
        assert audit.validation_warnings == ["trimmed whitespace"]

        ir_versions = db.execute(select(DiagramIR)).scalars().all()
        assert len(ir_versions) == 1
        assert ir_versions[0].svg_text == "<svg><text>system</text></svg>"

        tool_audit_id = tool_result["output"].get("audit_id")
        assert tool_audit_id == str(audit.id)
