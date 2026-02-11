"""Styling audit persistence helpers."""
from __future__ import annotations

from typing import Iterable, List
from uuid import UUID
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from src.db_models import StylingAudit


def _coerce_uuid(value: UUID | str | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, str(value))


def record_styling_audit(
    db: DbSession,
    *,
    session_id: UUID,
    plan_id: UUID | str | None = None,
    diagram_id: UUID | None,
    diagram_type: str | None,
    user_prompt: str | None,
    llm_format: str | None = None,
    llm_diagram: str | None = None,
    sanitized_diagram: str | None = None,
    extracted_intent: dict | None,
    styling_plan: dict | None,
    execution_steps: Iterable[str] | None,
    agent_reasoning: str | None,
    mode: str,
    renderer_input_before: str | None,
    renderer_input_after: str | None,
    svg_before: str | None,
    svg_after: str | None,
    validation_warnings: Iterable[str] | None = None,
    blocked_tokens: Iterable[str] | None = None,
) -> StylingAudit:
    normalized_mode = mode or "post-svg"
    audit = StylingAudit(
        session_id=session_id,
        plan_id=_coerce_uuid(plan_id),
        diagram_id=_coerce_uuid(diagram_id),
        diagram_type=diagram_type,
        user_prompt=user_prompt,
        llm_format=llm_format,
        llm_diagram=llm_diagram,
        sanitized_diagram=sanitized_diagram,
        extracted_intent=extracted_intent,
        styling_plan=styling_plan,
        execution_steps=list(execution_steps or []),
        agent_reasoning=agent_reasoning,
        mode="pre-svg" if normalized_mode.startswith("pre") else "post-svg",
        renderer_input_before=renderer_input_before,
        renderer_input_after=renderer_input_after,
        svg_before=svg_before,
        svg_after=svg_after,
        validation_warnings=list(validation_warnings or []),
        blocked_tokens=list(blocked_tokens or []),
    )
    db.add(audit)
    db.flush()
    return audit


def list_styling_audits(db: DbSession, diagram_id: UUID | str) -> List[StylingAudit]:
    stmt = (
        select(StylingAudit)
        .where(StylingAudit.diagram_id == _coerce_uuid(diagram_id))
        .order_by(StylingAudit.timestamp.desc())
    )
    return list(db.execute(stmt).scalars())


def get_styling_audit(db: DbSession, audit_id: UUID | str, diagram_id: UUID | str | None = None) -> StylingAudit | None:
    stmt = select(StylingAudit).where(StylingAudit.id == _coerce_uuid(audit_id))
    if diagram_id:
        stmt = stmt.where(StylingAudit.diagram_id == _coerce_uuid(diagram_id))
    return db.execute(stmt).scalars().first()


def assign_diagram_to_audit(db: DbSession, *, audit_id: UUID | str, diagram_id: UUID | str) -> StylingAudit | None:
    audit = db.get(StylingAudit, _coerce_uuid(audit_id))
    if not audit:
        return None
    target_diagram_id = _coerce_uuid(diagram_id)
    if audit.diagram_id == target_diagram_id:
        return audit
    audit.diagram_id = target_diagram_id
    db.flush()
    return audit


def list_audits_by_plan(db: DbSession, plan_id: UUID | str) -> List[StylingAudit]:
    stmt = (
        select(StylingAudit)
        .where(StylingAudit.plan_id == _coerce_uuid(plan_id))
        .order_by(StylingAudit.timestamp.desc())
    )
    return list(db.execute(stmt).scalars())


def attach_plan_to_audit(db: DbSession, *, audit_id: UUID | str, plan_id: UUID | str) -> StylingAudit | None:
    audit = db.get(StylingAudit, _coerce_uuid(audit_id))
    if not audit:
        return None
    coerced_plan = _coerce_uuid(plan_id)
    if audit.plan_id == coerced_plan:
        return audit
    audit.plan_id = coerced_plan
    db.flush()
    return audit
