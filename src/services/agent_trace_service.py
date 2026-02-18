"""Service for recording and querying agent decision traces."""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from src.db_models import AgentTrace

logger = logging.getLogger(__name__)


def _safe_uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_URL, str(value))


def _truncate_for_json(obj: Any, max_str_len: int = 2000) -> Any:
    """Recursively truncate long strings in a dict/list for safe JSON storage."""
    if isinstance(obj, str):
        return obj[:max_str_len] + "…" if len(obj) > max_str_len else obj
    if isinstance(obj, dict):
        return {k: _truncate_for_json(v, max_str_len) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_truncate_for_json(v, max_str_len) for v in obj]
    return obj


def record_trace(
    db: DbSession,
    *,
    session_id: UUID | str,
    agent_name: str,
    input_summary: Dict[str, Any] | None = None,
    output_summary: Dict[str, Any] | None = None,
    decision: str | None = None,
    reasoning: str | None = None,
    plan_id: UUID | str | None = None,
    step_index: int | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
) -> AgentTrace:
    """Record a single agent decision trace."""
    trace = AgentTrace(
        session_id=_safe_uuid(session_id),
        plan_id=_safe_uuid(plan_id),
        step_index=step_index,
        agent_name=agent_name,
        input_summary=_truncate_for_json(input_summary) if input_summary else None,
        output_summary=_truncate_for_json(output_summary) if output_summary else None,
        decision=decision[:256] if decision and len(decision) > 256 else decision,
        reasoning=reasoning,
        duration_ms=duration_ms,
        error=error,
    )
    db.add(trace)
    db.flush()
    return trace


@contextmanager
def trace_agent(
    db: DbSession,
    *,
    session_id: UUID | str,
    agent_name: str,
    input_summary: Dict[str, Any] | None = None,
    plan_id: UUID | str | None = None,
    step_index: int | None = None,
):
    """Context manager that times an agent call and records the trace.

    Usage::

        with trace_agent(db, session_id=sid, agent_name="planner", input_summary={...}) as t:
            result = do_work()
            t["output_summary"] = {...}
            t["decision"] = "edit_image"
    """
    ctx: Dict[str, Any] = {
        "output_summary": None,
        "decision": None,
        "reasoning": None,
        "error": None,
    }
    start = time.perf_counter()
    try:
        yield ctx
    except Exception as exc:
        ctx["error"] = str(exc)
        raise
    finally:
        elapsed = int((time.perf_counter() - start) * 1000)
        try:
            record_trace(
                db,
                session_id=session_id,
                agent_name=agent_name,
                input_summary=input_summary,
                output_summary=ctx.get("output_summary"),
                decision=ctx.get("decision"),
                reasoning=ctx.get("reasoning"),
                plan_id=plan_id,
                step_index=step_index,
                duration_ms=elapsed,
                error=ctx.get("error"),
            )
        except Exception:
            logger.debug("Failed to record agent trace", exc_info=True)


def list_traces_by_session(db: DbSession, session_id: UUID | str) -> Sequence[AgentTrace]:
    sid = _safe_uuid(session_id)
    return list(
        db.execute(
            select(AgentTrace)
            .where(AgentTrace.session_id == sid)
            .order_by(AgentTrace.created_at.asc())
        ).scalars()
    )


def list_traces_by_plan(db: DbSession, plan_id: UUID | str) -> Sequence[AgentTrace]:
    pid = _safe_uuid(plan_id)
    return list(
        db.execute(
            select(AgentTrace)
            .where(AgentTrace.plan_id == pid)
            .order_by(AgentTrace.created_at.asc())
        ).scalars()
    )
