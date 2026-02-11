import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db import Base
from src.db_models import Session as SessionRecord, StylingAudit
from src.mcp.registry import mcp_registry
from src.mcp.tools import register_mcp_tools
from src.schemas import MCPExecuteRequest
from src.server import mcp_discover_endpoint, mcp_execute_endpoint


test_engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    register_mcp_tools(mcp_registry)
    yield


@pytest.fixture
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _create_session_record(db_session):
    record = SessionRecord()
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def test_mcp_discover_includes_styling_tools():
    response = mcp_discover_endpoint()
    tool_ids = {tool.id for tool in response.tools}
    assert "styling.apply_pre_svg" in tool_ids
    assert "styling.apply_post_svg" in tool_ids


def test_mcp_execute_post_svg_records_audit(db_session):
    session_record = _create_session_record(db_session)
    payload = MCPExecuteRequest(
        tool_id="styling.apply_post_svg",
        args={
            "svgText": '<svg xmlns="http://www.w3.org/2000/svg"><text id="n1">Label</text></svg>',
            "stylingIntent": {"textStyle": {"fontWeight": "bold"}},
            "userPrompt": "Make text bold",
        },
        session_id=session_record.id,
    )

    response = mcp_execute_endpoint(payload, db=db_session)
    result = response.result

    assert result["success"] is True
    assert result["mode"] == "post-svg"
    assert "svgAfter" in result
    assert "auditId" in result

    audits = db_session.query(StylingAudit).all()
    assert len(audits) == 1
    assert audits[0].session_id == session_record.id
    assert audits[0].mode == "post-svg"


def test_mcp_execute_pre_svg_returns_renderer_input(db_session):
    session_record = _create_session_record(db_session)
    payload = MCPExecuteRequest(
        tool_id="styling.apply_pre_svg",
        args={
            "renderer": "mermaid",
            "rendererInput": {"source": "graph LR\nA-->B"},
            "stylingIntent": "Use blue nodes",
            "userPrompt": "Use blue nodes",
        },
        session_id=session_record.id,
    )

    response = mcp_execute_endpoint(payload, db=db_session)
    result = response.result

    assert result["success"] is True
    assert result["mode"] == "pre-svg"
    assert "rendererInputAfter" in result
    assert result["renderer"].lower() == "mermaid"
