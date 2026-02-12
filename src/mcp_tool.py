"""MCP tool adapter for diagram generation and feedback."""
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session as DbSession

from src.feedback_controller import process_feedback, get_ir, list_ir_history
from src.db_models import Image
from src.ir_v2 import make_ir_version
from src.ir_adapter import render_v2_svg
from src.animation.diagram_renderer import render_svg
from src.services.session_service import create_session, _create_ir_version, _create_image
from src.tools.svg_ir import render_ir_svg


def generate(diagram_spec: Dict[str, Any], *, db: DbSession) -> Dict[str, Any]:
    """Create diagram from a v2 IR spec. Returns {diagram_id, ir, artifacts}."""
    ir_wrapper = diagram_spec.get("ir") or diagram_spec.get("ir_wrapper") or diagram_spec
    if "ir" not in ir_wrapper:
        # wrap diagram directly
        ir_wrapper = make_ir_version(
            diagram_id=diagram_spec.get("diagram_id") or "diagram",
            ir={"diagram": diagram_spec.get("diagram") or diagram_spec},
        ).to_dict()

    session = create_session(db, title="MCP Diagram")
    svg_text = render_v2_svg(ir_wrapper)
    svg_text = render_svg(svg_text, animated=False, enhanced=True)
    ir_version = _create_ir_version(
        db,
        session,
        diagram_type=ir_wrapper.get("ir", {}).get("diagram", {}).get("type", "diagram"),
        svg_text=svg_text,
        reason="mcp_generate",
        parent_ir_id=None,
        ir_json={"ir_v2": ir_wrapper},
    )
    svg_file = render_ir_svg(svg_text, f"{session.id}_mcp_{ir_version.version}")
    image = _create_image(
        db,
        session,
        file_path=svg_file,
        prompt=None,
        reason="mcp_generate",
        parent_image_id=None,
        ir_id=ir_version.id,
    )
    db.commit()
    return {
        "diagram_id": str(image.id),
        "ir": ir_wrapper,
        "artifacts": [{"path": image.file_path, "type": "svg"}],
    }


def apply_feedback(feedback_payload: Dict[str, Any], *, db: DbSession) -> Dict[str, Any]:
    return process_feedback(db, feedback_payload)


def get_ir_payload(diagram_id: str, *, db: DbSession) -> Dict[str, Any]:
    return get_ir(db, diagram_id)


def get_ir_history_payload(diagram_id: str, *, db: DbSession) -> Dict[str, Any]:
    return {"history": list_ir_history(db, diagram_id)}


def export_svg(diagram_id: str, *, db: DbSession) -> Dict[str, Any]:
    image = db.get(Image, diagram_id)
    if not image:
        return {"error": "Image not found"}
    return {"path": image.file_path, "type": "svg"}


def export_gif(diagram_id: str, *, db: DbSession) -> Dict[str, Any]:
    image = db.get(Image, diagram_id)
    if not image:
        return {"error": "Image not found"}
    return {"error": "GIF export not implemented"}
