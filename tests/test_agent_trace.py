"""Tests for agent trace recording and querying."""
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db_models import Base, Session as DBSession, AgentTrace
from src.services.agent_trace_service import (
    record_trace,
    trace_agent,
    list_traces_by_session,
    list_traces_by_plan,
    _truncate_for_json,
    _safe_uuid,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def app_session(db):
    s = DBSession(title="trace-test")
    db.add(s)
    db.flush()
    return s


class TestRecordTrace:
    def test_basic_record(self, db, app_session):
        trace = record_trace(
            db,
            session_id=app_session.id,
            agent_name="planner",
            input_summary={"user_message": "hello"},
            output_summary={"intent": "generate_diagram"},
            decision="generate",
            duration_ms=42,
        )
        assert trace.id is not None
        assert trace.agent_name == "planner"
        assert trace.session_id == app_session.id
        assert trace.input_summary == {"user_message": "hello"}
        assert trace.output_summary == {"intent": "generate_diagram"}
        assert trace.decision == "generate"
        assert trace.duration_ms == 42
        assert trace.error is None

    def test_record_with_error(self, db, app_session):
        trace = record_trace(
            db,
            session_id=app_session.id,
            agent_name="tool.generate_plantuml",
            decision="error",
            error="Connection refused",
        )
        assert trace.error == "Connection refused"
        assert trace.decision == "error"

    def test_record_with_plan_and_step(self, db, app_session):
        plan_id = uuid.uuid4()
        trace = record_trace(
            db,
            session_id=app_session.id,
            agent_name="tool.edit_diagram_ir",
            plan_id=plan_id,
            step_index=2,
            input_summary={"instruction": "make API circular"},
            output_summary={"patch_ops_count": 1},
            decision="completed in 15ms",
            duration_ms=15,
        )
        assert trace.plan_id == plan_id
        assert trace.step_index == 2

    def test_decision_truncated_at_256(self, db, app_session):
        long_decision = "x" * 300
        trace = record_trace(
            db,
            session_id=app_session.id,
            agent_name="test",
            decision=long_decision,
        )
        assert len(trace.decision) == 256


class TestTraceAgent:
    def test_context_manager_success(self, db, app_session):
        with trace_agent(db, session_id=app_session.id, agent_name="test_cm") as ctx:
            ctx["output_summary"] = {"result": "ok"}
            ctx["decision"] = "success"

        traces = list_traces_by_session(db, app_session.id)
        assert len(traces) == 1
        assert traces[0].agent_name == "test_cm"
        assert traces[0].output_summary == {"result": "ok"}
        assert traces[0].duration_ms is not None
        assert traces[0].error is None

    def test_context_manager_error(self, db, app_session):
        with pytest.raises(ValueError):
            with trace_agent(db, session_id=app_session.id, agent_name="failing") as ctx:
                raise ValueError("boom")

        traces = list_traces_by_session(db, app_session.id)
        assert len(traces) == 1
        assert traces[0].error == "boom"


class TestListTraces:
    def test_by_session(self, db, app_session):
        for i in range(3):
            record_trace(db, session_id=app_session.id, agent_name=f"step_{i}")
        traces = list_traces_by_session(db, app_session.id)
        assert len(traces) == 3

    def test_by_plan(self, db, app_session):
        plan_id = uuid.uuid4()
        record_trace(db, session_id=app_session.id, agent_name="a", plan_id=plan_id)
        record_trace(db, session_id=app_session.id, agent_name="b", plan_id=plan_id)
        record_trace(db, session_id=app_session.id, agent_name="c")  # different plan
        traces = list_traces_by_plan(db, plan_id)
        assert len(traces) == 2

    def test_empty(self, db, app_session):
        traces = list_traces_by_session(db, app_session.id)
        assert traces == []


class TestHelpers:
    def test_truncate_for_json(self):
        result = _truncate_for_json({"long": "a" * 3000}, max_str_len=100)
        assert len(result["long"]) == 101  # 100 + "…"
        assert result["long"].endswith("…")

    def test_truncate_nested(self):
        result = _truncate_for_json({"items": [{"svg": "x" * 5000}]}, max_str_len=50)
        assert len(result["items"][0]["svg"]) == 51

    def test_safe_uuid_string(self):
        raw = "550e8400-e29b-41d4-a716-446655440000"
        assert _safe_uuid(raw) == uuid.UUID(raw)

    def test_safe_uuid_none(self):
        assert _safe_uuid(None) is None

    def test_safe_uuid_invalid(self):
        # should create a deterministic uuid5 fallback
        result = _safe_uuid("not-a-uuid")
        assert isinstance(result, uuid.UUID)


class TestTraceRelationship:
    def test_session_has_agent_traces(self, db, app_session):
        record_trace(db, session_id=app_session.id, agent_name="planner")
        record_trace(db, session_id=app_session.id, agent_name="tool.gen")
        db.refresh(app_session)
        assert len(app_session.agent_traces) == 2
        names = {t.agent_name for t in app_session.agent_traces}
        assert names == {"planner", "tool.gen"}
