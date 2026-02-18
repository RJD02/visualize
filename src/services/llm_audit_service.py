"""LLM audit logging service."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from src.db import SessionLocal
from src.db_models import LlmAudit


def _coerce_uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except Exception:
        return None


def _normalize_messages(messages: list[dict] | None) -> list[dict] | None:
    if not messages:
        return None
    normalized: list[dict] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        normalized.append({"role": role, "content": content})
    return normalized or None


def _extract_response_fields(response: Any) -> tuple[str | None, dict | None, dict | None]:
    if response is None:
        return None, None, None
    text = None
    try:
        choice = response.choices[0]
        text = getattr(choice.message, "content", None)
    except Exception:
        text = None
    usage = None
    try:
        usage_obj = getattr(response, "usage", None)
        if usage_obj is not None:
            usage = usage_obj.model_dump() if hasattr(usage_obj, "model_dump") else dict(usage_obj)
    except Exception:
        usage = None
    response_json = None
    try:
        response_json = {
            "id": getattr(response, "id", None),
            "created": getattr(response, "created", None),
            "model": getattr(response, "model", None),
        }
        if usage is not None:
            response_json["usage"] = usage
    except Exception:
        response_json = None
    return text, response_json, usage


def record_llm_audit(
    db: DbSession | None,
    *,
    session_id: str | UUID | None = None,
    plan_id: str | UUID | None = None,
    tool_name: str | None = None,
    model: str | None = None,
    messages: list[dict] | None = None,
    response: Any | None = None,
    error: str | None = None,
    metadata: dict | None = None,
) -> None:
    session_uuid = _coerce_uuid(session_id)
    plan_uuid = _coerce_uuid(plan_id)
    text, response_json, usage = _extract_response_fields(response)
    normalized_messages = _normalize_messages(messages)

    def _write(db_session: DbSession) -> None:
        audit = LlmAudit(
            session_id=session_uuid,
            plan_id=plan_uuid,
            tool_name=tool_name,
            model=model,
            messages=normalized_messages,
            response_text=text,
            response_json=response_json,
            usage=usage,
            metadata_json=metadata,
            error=error,
        )
        db_session.add(audit)
        db_session.commit()

    if db is not None:
        try:
            _write(db)
        except Exception:
            pass
        return

    db_session = SessionLocal()
    try:
        try:
            _write(db_session)
        except Exception:
            pass
    finally:
        db_session.close()
