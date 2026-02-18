"""Feedback controller for IR mutation and regeneration."""
from __future__ import annotations

import uuid as _uuid
from typing import Any, Dict
from sqlalchemy.orm import Session as DbSession

from src.db_models import DiagramIR, Image, Message, Session
from src.ir_v2 import make_ir_version, diff_summary
from src.ir_adapter import render_v2_svg, v2_from_svg
from src.ir_transforms import apply_feedback
from src.animation.diagram_renderer import render_svg
from src.services.session_service import _create_ir_version, _create_image, _infer_diagram_type, create_session
from src.tools.svg_ir import render_ir_svg


class FeedbackError(Exception):
    pass


def _to_uuid(value: str | _uuid.UUID) -> _uuid.UUID:
    """Convert a string to a uuid.UUID if needed (DB columns are UUID)."""
    if isinstance(value, _uuid.UUID):
        return value
    try:
        return _uuid.UUID(str(value))
    except (ValueError, AttributeError) as exc:
        raise FeedbackError(f"Invalid UUID: {value}") from exc


def _load_image(db: DbSession, diagram_id: str) -> Image:
    image = db.get(Image, _to_uuid(diagram_id))
    if not image:
        raise FeedbackError("Image not found")
    return image


def _load_ir_wrapper(db: DbSession, image: Image) -> Dict[str, Any]:
    ir_record = db.get(DiagramIR, image.ir_id) if image.ir_id else None
    if ir_record and isinstance(ir_record.ir_json, dict):
        ir_v2 = ir_record.ir_json.get("ir_v2")
        if isinstance(ir_v2, dict):
            return ir_v2
        # Allow v2 stored at root
        if {"diagram_id", "ir_version", "parent_version", "ir"}.issubset(ir_record.ir_json.keys()):
            return ir_record.ir_json
    if ir_record and ir_record.svg_text:
        return v2_from_svg(ir_record.svg_text, diagram_id=str(image.id))
    if image.file_path and image.file_path.endswith(".svg"):
        try:
            from src.utils.file_utils import read_text_file

            svg_text = read_text_file(image.file_path)
            return v2_from_svg(svg_text, diagram_id=str(image.id))
        except Exception as exc:
            raise FeedbackError(f"Unable to load SVG for IR: {exc}") from exc
    raise FeedbackError("No IR or SVG available")


def process_feedback(db: DbSession, payload: Dict[str, Any]) -> Dict[str, Any]:
    diagram_id = payload.get("diagram_id")
    if not diagram_id:
        raise FeedbackError("diagram_id is required")
    image = _load_image(db, diagram_id)
    session = db.get(Session, image.session_id)
    if not session:
        raise FeedbackError("Session not found")

    wrapper = _load_ir_wrapper(db, image)
    before_wrapper = dict(wrapper)
    action = payload.get("action")
    if not action:
        raise FeedbackError("action is required")

    updated_ir, patches = apply_feedback(payload, wrapper)
    parent_version = wrapper.get("ir_version")
    new_wrapper = make_ir_version(
        diagram_id=str(image.id),
        ir=updated_ir.get("ir") or updated_ir,
        parent_version=parent_version,
    ).to_dict()

    svg_text = render_v2_svg(new_wrapper)
    svg_text = render_svg(svg_text, animated=False, enhanced=True)

    diagram_type = _infer_diagram_type(image.file_path)
    ir_version = _create_ir_version(
        db,
        session,
        diagram_type=diagram_type,
        svg_text=svg_text,
        reason="feedback",
        parent_ir_id=image.ir_id,
        ir_json={
            "ir_v2": new_wrapper,
            "feedback_audit": {
                "feedback": payload,
                "mutation_plan": patches,
                "ir_before": before_wrapper,
                "ir_after": new_wrapper,
                "diff_summary": diff_summary(before_wrapper.get("ir", {}), new_wrapper.get("ir", {})),
                "confidence": 1.0,
            },
        },
    )
    svg_file = render_ir_svg(svg_text, f"{session.id}_{diagram_type}_{ir_version.version}")
    created_image = _create_image(
        db,
        session,
        file_path=svg_file,
        prompt=None,
        reason="feedback",
        parent_image_id=image.id,
        ir_id=ir_version.id,
    )
    db.add(
        Message(
            session_id=session.id,
            role="assistant",
            content="",
            intent="feedback",
            image_id=created_image.id,
            message_type="image",
            image_version=created_image.version,
            diagram_type=diagram_type,
            ir_id=ir_version.id,
        )
    )
    db.commit()
    db.refresh(created_image)

    return {
        "status": "ok",
        "diagram_id": str(image.id),
        "image_id": str(created_image.id),
        "ir": new_wrapper,
        "artifacts": [{"path": created_image.file_path, "type": "svg"}],
    }


def list_ir_history(db: DbSession, diagram_id: str) -> list[Dict[str, Any]]:
    image = _load_image(db, diagram_id)
    if not image.ir_id:
        return []
    rows = (
        db.query(DiagramIR)
        .filter(DiagramIR.session_id == image.session_id)
        .order_by(DiagramIR.version.desc())
        .all()
    )
    payloads = []
    for ir in rows:
        if not ir.ir_json:
            continue
        ir_v2 = ir.ir_json.get("ir_v2") if isinstance(ir.ir_json, dict) else None
        if ir_v2:
            payloads.append(ir_v2)
    return payloads


def get_ir(db: DbSession, diagram_id: str) -> Dict[str, Any]:
    image = _load_image(db, diagram_id)
    return _load_ir_wrapper(db, image)


def create_demo_diagram(db: DbSession) -> Dict[str, Any]:
    session = create_session(db, title="Demo Session")
    wrapper = {
        "diagram_id": "demo-diagram",
        "ir_version": 1,
        "parent_version": None,
        "ir": {
            "diagram": {
                "id": "demo-diagram",
                "type": "system_architecture",
                "blocks": [
                    {
                        "id": "block-client",
                        "type": "actor",
                        "text": "Client",
                        "bbox": {"x": 40, "y": 60, "w": 140, "h": 48},
                        "style": {},
                        "annotations": {},
                        "version": 1,
                    },
                    {
                        "id": "block-api",
                        "type": "component",
                        "text": "API",
                        "bbox": {"x": 260, "y": 60, "w": 140, "h": 48},
                        "style": {},
                        "annotations": {},
                        "version": 1,
                    },
                ],
                "relations": [
                    {"from": "block-client", "to": "block-api", "label": "calls"}
                ],
            }
        },
    }
    svg_text = render_v2_svg(wrapper)
    svg_text = render_svg(svg_text, animated=False, enhanced=True)
    ir_version = _create_ir_version(
        db,
        session,
        diagram_type="system_context",
        svg_text=svg_text,
        reason="demo",
        parent_ir_id=None,
        ir_json={"ir_v2": wrapper},
    )
    svg_file = render_ir_svg(svg_text, f"{session.id}_system_context_{ir_version.version}")
    created_image = _create_image(
        db,
        session,
        file_path=svg_file,
        prompt=None,
        reason="demo",
        parent_image_id=None,
        ir_id=ir_version.id,
    )
    db.add(
        Message(
            session_id=session.id,
            role="user",
            content="demo diagram",
            intent="demo",
            image_id=None,
            message_type="text",
            image_version=None,
            diagram_type=None,
            ir_id=None,
        )
    )
    db.add(
        Message(
            session_id=session.id,
            role="assistant",
            content="",
            intent="demo",
            image_id=created_image.id,
            message_type="image",
            image_version=created_image.version,
            diagram_type="system_context",
            ir_id=ir_version.id,
        )
    )
    db.commit()
    db.refresh(created_image)
    return {
        "session_id": str(session.id),
        "image_id": str(created_image.id),
        "diagram_id": str(created_image.id),
    }
