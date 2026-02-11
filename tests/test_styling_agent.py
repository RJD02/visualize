import re
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db import Base
from src.mcp.registry import mcp_registry
from src.mcp.tools import register_mcp_tools, tool_svg_styling_agent
from src.services import session_service
from src.services.styling_audit_service import list_styling_audits, assign_diagram_to_audit

register_mcp_tools(mcp_registry)


def test_mermaid_pre_style_simple_color_request():
    source = "graph LR\nA-->B"
    prompt = "Generate a flowchart with orange and yellow blocks."
    res = mcp_registry.execute(
        "styling.apply_pre_svg",
        {
            "renderer": "mermaid",
            "rendererInput": {"source": source},
            "userPrompt": prompt,
            "stylingIntent": prompt,
        },
        {},
    )
    assert res["success"]
    assert res.get("mode") == "pre-svg"
    text = res.get("rendererInputAfter", "")
    # Expect mermaid init themeVariables or classDef to be present
    assert "themeVariables" in text or "classDef" in text


def test_post_svg_text_styling():
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><text id="t1">Label</text><rect id="r1"/></svg>'
    intent = {"textStyle": {"fontWeight": "bold", "fontColor": "#444444"}}
    res = mcp_registry.execute(
        "styling.apply_post_svg",
        {"svgText": svg, "stylingIntent": intent, "userPrompt": "Make labels bold"},
        {},
    )
    assert res["success"]
    assert res.get("mode") == "post-svg"
    out = res["svgAfter"]
    # Inline font-weight or style rule should be applied
    assert "font-weight" in out or "fill: #444444" in out


def test_edge_styling_post_svg():
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><path id="e1" d="M0,0 L10,10"/></svg>'
    res = mcp_registry.execute(
        "styling.apply_post_svg",
        {
            "svgText": svg,
            "stylingIntent": "Make edges thick and blue.",
            "userPrompt": "Make edges thick and blue.",
        },
        {},
    )
    assert res["success"]
    assert res.get("mode") == "post-svg"
    out = res["svgAfter"]
    assert ("stroke:" in out and "#0000FF" in out) or ("stroke-width" in out)


def test_ambiguous_pastel_palette_applied():
    prompt = "Use a pastel theme."
    res = mcp_registry.execute(
        "styling.apply_pre_svg",
        {
            "renderer": "mermaid",
            "rendererInput": {"source": "graph LR\nA-->B"},
            "stylingIntent": prompt,
            "userPrompt": prompt,
        },
        {},
    )
    assert res["success"]
    assert res.get("mode") == "pre-svg"
    txt = res.get("rendererInputAfter", "")
    assert "themeVariables" in txt


def test_compound_request_sequence_diagram():
    prompt = "Create a sequence diagram with green blocks and light text."
    res = mcp_registry.execute(
        "styling.apply_pre_svg",
        {
            "renderer": "plantuml",
            "rendererInput": {"source": "@startuml\nAlice->Bob: Hello\n@enduml"},
            "stylingIntent": prompt,
            "userPrompt": prompt,
        },
        {},
    )
    assert res["success"]
    txt = res.get("rendererInputAfter", "")
    assert "skinparam" in txt or "<style>" in txt


def test_styling_agent_records_audit(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        session = session_service.create_session(db)
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="100" height="40"/></svg>'
        res = tool_svg_styling_agent(
            context={"db": db, "session": session, "session_id": str(session.id), "user_message": "Use orange blocks"},
            svg_text=svg,
            styling_intent="Use orange blocks",
            diagram_id="diagram-test",
            diagram_type="system_context",
            user_prompt="Use orange blocks",
        )
        assert res["success"]
        audits = list_styling_audits(db, diagram_id="diagram-test")
        assert len(audits) == 1
        assert res.get("audit_id") == str(audits[0].id)
        assert audits[0].mode == "post-svg"


def test_assign_diagram_updates_audit():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        session = session_service.create_session(db)
        res = tool_svg_styling_agent(
            context={"db": db, "session": session, "session_id": str(session.id)},
            renderer="plantuml",
            renderer_input={"source": "@startuml\n@enduml", "diagram_type": "system_context"},
            styling_intent="Use pastel theme",
            diagram_type="system_context",
            user_prompt="Use pastel theme",
        )
        assert res["success"]
        audit_id = res.get("audit_id")
        assign_diagram_to_audit(db, audit_id=audit_id, diagram_id="img-1")
        audits = list_styling_audits(db, diagram_id="img-1")
        assert len(audits) == 1
        assert audits[0].mode == "pre-svg"
