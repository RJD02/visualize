import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db import Base
from src.services import session_service


def _fake_arch_plan():
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
        "visual_hints": {"layout": "left-to-right", "group_by_zone": True, "external_dashed": True},
    }


class FakePlanner:
    def plan(self, message, state, tools):
        # Return a plan that ingests the repo and generates diagrams
        return {
            "intent": "regenerate",
            "diagram_count": None,
            "diagrams": [{"type": "sequence", "reason": "user requested"}],
            "target_image_id": None,
            "target_diagram_type": "sequence",
            "instructions": message,
            "requires_regeneration": True,
            "plan": [
                {"tool": "ingest_github_repo", "arguments": {"repo_url": message}},
                {"tool": "generate_architecture_plan", "arguments": {}},
                {"tool": "generate_multiple_diagrams", "arguments": {}},
            ],
        }


def fake_execute(name, args, context=None):
    # Simulate minimal tool outputs
    if name == "ingest_github_repo":
        return {"repo_url": args.get("repo_url"), "commit": "deadbeef", "summary": "repo summary", "content": "repo files"}
    if name == "generate_architecture_plan":
        return {"architecture_plan": _fake_arch_plan()}
    if name == "generate_multiple_diagrams":
        # Return a simple SVG for sequence diagram
        svg = "<svg xmlns=\"http://www.w3.org/2000/svg\"><text>sequence</text></svg>"
        return {"ir_entries": [{"diagram_type": "sequence", "svg": svg, "svg_file": None}]}
    return {}


def test_handle_creates_svg_for_mermaid(monkeypatch, tmp_path):
    # Create isolated sqlite DB
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    # Patch planner and MCP registry execute
    monkeypatch.setattr(session_service, "ConversationPlannerAgent", FakePlanner)
    monkeypatch.setattr(session_service, "mcp_registry", session_service.mcp_registry)
    monkeypatch.setattr(session_service.mcp_registry, "execute", fake_execute)

    with SessionLocal() as db:
        sess = session_service.create_session(db)
        # Simulate user message with GitHub URL and mermaid request
        message = "https://github.com/RJD02/job-portal-go\nCan you generate a sequence diagram through mermaid for this GitHub repo"
        result = session_service.handle_message(db, sess, message)

        # Ensure response indicates generation intent
        assert result.get("intent") in {"generate", "regenerate", "generate_sequence"} or result.get("plan")

        images = session_service.list_images(db, sess.id)
        irs = session_service.list_ir_versions(db, sess.id)

        # Expect at least one IR version with SVG text
        assert len(irs) >= 1
        assert any((ir.svg_text or "").strip().startswith("<svg") for ir in irs)

        # Expect image(s) created for diagrams
        assert len(images) >= 1
        # If images have file paths, ensure svg or svg_text stored in IR
        for img in images:
            assert img.file_path is not None
            assert img.file_path.endswith(".svg") or any((ir.svg_text or "").strip().startswith("<svg") for ir in irs)
