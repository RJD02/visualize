"""Session and conversation orchestration service."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from src.db_models import (
    ArchitecturePlan as ArchitecturePlanRecord,
    DiagramFile,
    DiagramIR,
    Image,
    Message,
    PlanExecution,
    PlanRecord,
    Session,
)
from src.models.architecture_plan import ArchitecturePlan as ArchitecturePlanModel
from src.agents.conversation_planner_agent import ConversationPlannerAgent, LATEST_IMAGE_PLACEHOLDER
from src.mcp.registry import mcp_registry
from src.mcp.tools import register_mcp_tools, apply_ir_node_styles_to_svg
from src.orchestrator.adk_workflow import ADKWorkflow
from src.services.intent import explain_architecture
from src.services.styling_audit_service import record_styling_audit
from src.services.agent_trace_service import record_trace, trace_agent
from src.tools.file_storage import save_json
from src.tools.text_extractor import extract_text
from src.tools.svg_ir import generate_svg_from_plan, render_ir_svg, build_ir_from_plan, ZONE_TITLES
from src.tools.plantuml_renderer import generate_plantuml_from_plan, render_diagrams
from src.tools.plantuml_renderer import render_llm_plantuml
from src.tools.mermaid_renderer import render_llm_mermaid
from src.utils.config import settings
from src.intent import generate_semantic_intent
from src.intent.diagram_intent import detect_intent
from src.intent.semantic_to_structural import (
    architecture_ir_from_plan,
    architecture_to_structural,
    story_ir_from_text,
    story_to_structural,
    sequence_ir_from_text,
    sequence_to_structural,
)
from src.renderers.router import render_ir
from src.ir.plan_to_semantic import plan_to_semantic_ir
from src.ir.plantuml_adapter import ir_to_plantuml
from src.renderer import render_plantuml, render_plantuml_svg
from xml.etree import ElementTree as ET
import json
from src.utils.file_utils import read_text_file
import logging
import time
from src.intent.semantic_aesthetic_ir import SemanticAestheticIR
from src.tools.diagram_validator import DiagramValidationError
from src.tools.ir_enricher import enrich_ir, IREnrichmentError


logger = logging.getLogger(__name__)


def _ensure_ir_metadata(svg_text: str, payload: dict) -> str:
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError:
        return svg_text
    has_meta = False
    for elem in root.iter():
        if elem.tag.endswith("metadata") and (elem.get("id") == "ir_metadata" or (elem.text and "diagram_type" in elem.text)):
            has_meta = True
            break
    if not has_meta:
        meta = ET.Element("metadata", {"id": "ir_metadata"})
        meta.text = json.dumps(payload)
        root.insert(0, meta)
    return ET.tostring(root, encoding="unicode")


def _enrich_ir_from_plan(plan_data: Dict[str, Any], diagram_type: str) -> Dict[str, Any] | None:
    if not plan_data or not settings.enable_ir_enrichment:
        return None

    try:
        normalized = json.loads(json.dumps(plan_data))
    except (TypeError, ValueError):
        if isinstance(plan_data, dict):
            normalized = dict(plan_data)
        else:
            return None

    if not isinstance(normalized, dict):
        return None

    normalized = dict(normalized)
    normalized["diagram_type"] = diagram_type

    try:
        return enrich_ir(normalized)
    except IREnrichmentError as exc:
        logger.warning(
            "IR enrichment failed", extra={"diagram_type": diagram_type, "error": str(exc)}
        )
    except Exception:
        logger.exception("Unexpected error during IR enrichment", extra={"diagram_type": diagram_type})
    return None


def _metadata_from_plan_or_default(plan_data: Dict[str, Any] | None, diagram_type: str) -> Dict[str, Any]:
    enriched = None
    if plan_data:
        enriched = _enrich_ir_from_plan(plan_data, diagram_type)
    if enriched:
        return enriched
    return {
        "diagram_type": diagram_type or "diagram",
        "layout": "top-down",
        "zone_order": list(ZONE_TITLES.keys()),
        "nodes": [],
        "edges": [],
        "nodeIntent": {},
        "edgeIntent": {},
        "globalIntent": {
            "palette": ["#FDE68A", "#FBCFE8", "#E0E7FF", "#DB2777", "#0F172A"],
            "layout": "top-down",
            "density": "balanced",
            "mood": "minimal",
        },
        "metadata": {
            "generated_by": "session_service-fallback",
            "spec_version": "v34",
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "validation": [{"severity": "warning", "message": "Fallback metadata; enrichment unavailable"}],
        },
    }

def save_edited_ir(db: DbSession, image_id: str, svg_text: str, reason: str = "edited via ui") -> Image:
    image = db.get(Image, image_id)
    if not image:
        raise ValueError("Image not found")
    session = db.get(Session, image.session_id)
    if not session:
        raise ValueError("Session for image not found")

    diagram_type = _infer_diagram_type(image.file_path)
    parent_ir_id = getattr(image, "ir_id", None)
    inherited_ir_json = None
    if parent_ir_id:
        parent_ir = db.get(DiagramIR, parent_ir_id)
        if parent_ir and parent_ir.ir_json:
            inherited_ir_json = dict(parent_ir.ir_json)
    ir_version = _create_ir_version(
        db,
        session,
        diagram_type=diagram_type,
        svg_text=svg_text,
        reason=reason,
        parent_ir_id=parent_ir_id,
        ir_json=inherited_ir_json,
    )
    svg_file = render_ir_svg(svg_text, f"{session.id}_{diagram_type}_{ir_version.version}")
    created_image = _create_image(
        db,
        session,
        file_path=svg_file,
        prompt=None,
        reason=reason,
        parent_image_id=image.id,
        ir_id=ir_version.id,
    )
    db.add(
        Message(
            session_id=session.id,
            role="assistant",
            content="",
            intent="edit",
            image_id=created_image.id,
            message_type="image",
            image_version=created_image.version,
            diagram_type=diagram_type,
            ir_id=ir_version.id,
        )
    )
    db.commit()
    db.refresh(created_image)
    return created_image


def create_session(db: DbSession, title: str | None = None) -> Session:
    session = Session(title=title or "Architecture Session")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session(db: DbSession, session_id: UUID | str) -> Session | None:
    if isinstance(session_id, str):
        try:
            session_id = UUID(session_id)
        except ValueError:
            return None
    return db.get(Session, session_id)


def list_messages(db: DbSession, session_id: UUID) -> List[Message]:
    return list(db.execute(select(Message).where(Message.session_id == session_id).order_by(Message.created_at)).scalars())


def list_images(db: DbSession, session_id: UUID) -> List[Image]:
    return list(db.execute(select(Image).where(Image.session_id == session_id).order_by(Image.version)).scalars())


def list_diagrams(db: DbSession, session_id: UUID) -> List[DiagramFile]:
    return list(db.execute(select(DiagramFile).where(DiagramFile.session_id == session_id)).scalars())


def list_ir_versions(db: DbSession, session_id: UUID) -> List[DiagramIR]:
    return list(db.execute(select(DiagramIR).where(DiagramIR.session_id == session_id).order_by(DiagramIR.version)).scalars())


def get_latest_plan(db: DbSession, session_id: UUID) -> ArchitecturePlanRecord | None:
    return db.execute(
        select(ArchitecturePlanRecord)
        .where(ArchitecturePlanRecord.session_id == session_id)
        .order_by(ArchitecturePlanRecord.created_at.desc())
    ).scalars().first()


def list_plan_records(db: DbSession, session_id: UUID) -> List[PlanRecord]:
    return list(
        db.execute(
            select(PlanRecord)
            .where(PlanRecord.session_id == session_id)
            .order_by(PlanRecord.created_at.desc())
        ).scalars()
    )


def ingest_input(
    db: DbSession,
    session: Session,
    files: Optional[List[str]],
    text: Optional[str],
    github_url: Optional[str] = None,
    generate_images: bool = True,
) -> dict:
    if not files and not text and not github_url:
        raise ValueError("Provide files, text, or github_url")

    content = None
    if github_url:
        if not mcp_registry.get_tool("ingest_github_repo"):
            register_mcp_tools(mcp_registry)
        tool_output = mcp_registry.execute("ingest_github_repo", {"repo_url": github_url}, context={"db": db})
        content = tool_output.get("content")
        session.source_repo = tool_output.get("repo_url")
        session.source_commit = tool_output.get("commit")
    if not content:
        content = extract_text(files=files, text=text)
    intent_result = detect_intent(content, github_url=github_url, has_files=bool(files))
    session.input_text = content

    workflow = ADKWorkflow()
    result: Dict[str, Any] = {}
    if intent_result.primary in {"story", "sequence"}:
        result["architecture_plan"] = None
    else:
        result = workflow.run(files=None, text=content, output_name=str(session.id))

    if result.get("architecture_plan"):
        plan_data = result["architecture_plan"]
        plan = ArchitecturePlanRecord(session_id=session.id, data=plan_data)
        db.add(plan)
        db.flush()
        logger.info(
            "Stored architecture plan",
            extra={
                "session_id": str(session.id),
                "diagram_views": plan_data.get("diagram_views", []),
                "zones": list((plan_data.get("zones") or {}).keys()),
            },
        )
        save_json(f"{session.id}_architecture_plan.json", plan_data)

    plan_data = result.get("architecture_plan") or {}
    plan_model: ArchitecturePlanModel | None = None
    if plan_data:
        plan_model = ArchitecturePlanModel.model_validate(plan_data)

    metadata_cache: Dict[str, Dict[str, Any]] = {}

    def _diagram_metadata_payload(diagram_type: str | None) -> Dict[str, Any]:
        key = diagram_type or "diagram"
        if key in metadata_cache:
            return metadata_cache[key]

        if plan_data:
            enriched = _enrich_ir_from_plan(plan_data, key)
            if enriched:
                metadata_cache[key] = enriched
                return enriched

        base_layout = "top-down"
        if plan_model and getattr(plan_model, "visual_hints", None):
            base_layout = plan_model.visual_hints.layout or base_layout

        payload: Dict[str, Any] = {
            "diagram_type": key,
            "layout": base_layout,
            "zone_order": list(ZONE_TITLES.keys()),
            "nodes": [],
            "edges": [],
        }

        if plan_model:
            try:
                ir_model = build_ir_from_plan(plan_model, key)
                payload = {
                    "diagram_type": ir_model.diagram_type,
                    "layout": ir_model.layout,
                    "zone_order": list(ir_model.zone_order),
                    "nodes": [
                        {
                            "node_id": node.node_id,
                            "label": node.label,
                            "role": node.role,
                            "zone": node.zone,
                        }
                        for node in (ir_model.nodes or [])
                    ],
                    "edges": [
                        {
                            "edge_id": edge.edge_id,
                            "from_id": edge.from_id,
                            "to_id": edge.to_id,
                            "rel_type": edge.rel_type,
                        }
                        for edge in (ir_model.edges or [])
                    ],
                }
            except Exception:
                pass

        metadata_cache[key] = payload
        return payload

    if not settings.enable_ir:
        if plan_data:
            diagrams = generate_plantuml_from_plan(plan_model)
            files = render_diagrams(diagrams, f"{session.id}", output_format="svg")
            if generate_images:
                for file_path in files:
                    diagram_type = _infer_diagram_type(file_path)
                    image = _create_image(
                        db,
                        session,
                        file_path=file_path,
                        prompt=None,
                        reason=f"diagram: {diagram_type}",
                    )
                    db.add(
                        Message(
                            session_id=session.id,
                            role="assistant",
                            content="",
                            intent="generate",
                            image_id=image.id,
                            message_type="image",
                            image_version=image.version,
                            diagram_type=diagram_type,
                        )
                    )
            else:
                # When not generating images (e.g., API ingest), just return diagram file paths
                result["images"] = files
    else:
        if intent_result.primary == "story":
            story_ir = story_ir_from_text(content)
            structural_ir = story_to_structural(story_ir)
            svg_text, choice = render_ir(structural_ir)
            svg_text = _ensure_ir_metadata(svg_text, {
                "diagram_type": "story",
                "layout": structural_ir.layout,
                "zone_order": [],
                "nodes": [],
                "edges": [],
            })
            ir_version = _create_ir_version(
                db,
                session,
                diagram_type="story",
                svg_text=svg_text,
                reason="story intent",
                parent_ir_id=None,
                ir_json={"intent": "story", "semantic_ir": story_ir.to_dict(), "structural_ir": structural_ir.to_dict(), "renderer": choice.renderer},
            )
            svg_file = render_ir_svg(svg_text, f"{session.id}_story_1")
            image = _create_image(
                db,
                session,
                file_path=svg_file,
                prompt=None,
                reason="diagram: story",
                ir_id=ir_version.id,
            )
            db.add(
                Message(
                    session_id=session.id,
                    role="assistant",
                    content="",
                    intent="generate",
                    image_id=image.id,
                    message_type="image",
                    image_version=image.version,
                    diagram_type="story",
                    ir_id=ir_version.id,
                )
            )
        elif intent_result.primary == "sequence":
            seq_ir = sequence_ir_from_text(content)
            structural_ir = sequence_to_structural(seq_ir)
            svg_text, choice = render_ir(structural_ir)
            svg_text = _ensure_ir_metadata(svg_text, {
                "diagram_type": "sequence",
                "layout": structural_ir.layout,
                "zone_order": [],
                "nodes": [],
                "edges": [],
            })
            ir_version = _create_ir_version(
                db,
                session,
                diagram_type="sequence",
                svg_text=svg_text,
                reason="sequence intent",
                parent_ir_id=None,
                ir_json={"intent": "sequence", "semantic_ir": seq_ir.to_dict(), "structural_ir": structural_ir.to_dict(), "renderer": choice.renderer},
            )
            svg_file = render_ir_svg(svg_text, f"{session.id}_sequence_1")
            image = _create_image(
                db,
                session,
                file_path=svg_file,
                prompt=None,
                reason="diagram: sequence",
                ir_id=ir_version.id,
            )
            db.add(
                Message(
                    session_id=session.id,
                    role="assistant",
                    content="",
                    intent="generate",
                    image_id=image.id,
                    message_type="image",
                    image_version=image.version,
                    diagram_type="sequence",
                    ir_id=ir_version.id,
                )
            )
        elif plan_data:
            # Use old working PlantUML generation - Structurizr renderer is broken
            if github_url:
                diagram_types = ["system_context", "container", "component"]
            else:
                diagram_types = plan_model.diagram_views or ["system_context"]
            
            # Generate using PlantUML directly (old working method)
            diagrams = generate_plantuml_from_plan(plan_model)
            files = render_diagrams(diagrams, f"{session.id}")
            
            for idx, (diagram_type, file_path) in enumerate(zip(diagram_types, files)):
                # Read the SVG content
                try:
                    svg_text = read_text_file(str(Path(file_path)))
                except Exception:
                    svg_text = Path(file_path).read_text(encoding="utf-8", errors="ignore")

                metadata_payload = _diagram_metadata_payload(diagram_type)
                svg_text = _ensure_ir_metadata(svg_text, metadata_payload)

                ir_payload: Dict[str, Any] = {"intent": diagram_type}
                if metadata_payload:
                    ir_payload["enriched_ir"] = metadata_payload

                ir_version = _create_ir_version(
                    db,
                    session,
                    diagram_type=diagram_type,
                    svg_text=svg_text,
                    reason="architecture intent",
                    parent_ir_id=None,
                    ir_json=ir_payload,
                )
                
                if generate_images:
                    image = _create_image(
                        db,
                        session,
                        file_path=file_path,
                        prompt=None,
                        reason=f"diagram: {diagram_type}",
                        parent_image_id=None,
                        ir_id=ir_version.id,
                    )
                    db.add(
                        Message(
                            session_id=session.id,
                            role="assistant",
                            content="",
                            intent="generate",
                            image_id=image.id,
                            message_type="image",
                            image_version=image.version,
                            diagram_type=diagram_type,
                            ir_id=ir_version.id,
                        )
                    )
                else:
                    # collect generated file paths when images aren't created
                    result.setdefault("images", []).append(file_path)
        else:
            db.add(
                Message(
                    session_id=session.id,
                    role="assistant",
                    content="Generated architecture.",
                    intent="generate",
                    message_type="text",
                )
            )
    db.commit()
    return result


def _build_planner_context(db: DbSession, session: Session) -> tuple[dict, dict]:
    plan = get_latest_plan(db, session.id)
    images = list_images(db, session.id)
    diagrams = list_diagrams(db, session.id)
    ir_versions = list_ir_versions(db, session.id)
    all_messages = list_messages(db, session.id)
    history = [{"role": m.role, "content": m.content} for m in all_messages[-10:]]
    state = {
        "active_image_id": str(images[-1].id) if images else None,
        "diagram_types": [d.diagram_type for d in diagrams] or [ir.diagram_type for ir in ir_versions],
        "images": [
            {
                "id": str(img.id),
                "version": img.version,
                "reason": img.reason,
                "file_path": img.file_path,
            }
            for img in images
        ],
        "history": history,
        "github_url": session.source_repo,
        "input_text": session.input_text,
        "architecture_plan": plan.data if plan else None,
    }
    cache = {
        "latest_plan": plan,
        "images": images,
        "diagrams": diagrams,
        "ir_versions": ir_versions,
        "messages": all_messages,
    }
    return state, cache


def _prepare_tool_arguments(
    db: DbSession,
    session: Session,
    plan_result: dict,
    tool_name: str,
    base_args: dict | None,
    message: str,
) -> tuple[dict, str | None]:
    args = dict(base_args or {})
    diagram_count = plan_result.get("diagram_count")
    planned_diagrams = plan_result.get("diagrams") or []
    planned_types = [d.get("type") for d in planned_diagrams if isinstance(d, dict) and d.get("type")]

    if tool_name in {
        "generate_plantuml",
        "generate_diagram",
        "edit_diagram_via_semantic_understanding",
    }:
        args.setdefault("output_name", f"{session.id}_{_next_version(db, session.id)}")

    if tool_name in {
        "generate_plantuml",
        "generate_diagram",
        "edit_diagram_via_semantic_understanding",
        "render_image_from_plan",
        "explain_architecture",
        "generate_sequence_from_architecture",
        "generate_plantuml_sequence",
    }:
        if not args.get("architecture_plan"):
            latest_plan = get_latest_plan(db, session.id)
            if latest_plan:
                args["architecture_plan"] = latest_plan.data
            else:
                return args, "I need an architecture plan to do that. Please generate one first."

    if tool_name == "generate_sequence_from_architecture":
        if "github_url" not in args and session.source_repo:
            args["github_url"] = session.source_repo
        args.setdefault("user_message", message)
        args.setdefault("output_name", f"{session.id}_sequence_{_next_version(db, session.id)}")

    if tool_name == "generate_plantuml_sequence":
        args.setdefault("output_name", f"{session.id}_sequence_{_next_version(db, session.id)}")

    if tool_name == "generate_architecture_plan" and "content" not in args:
        if session.input_text:
            args["content"] = session.input_text
        else:
            args["content"] = message

    if tool_name == "edit_existing_image" and "image_id" not in args:
        images = list_images(db, session.id)
        if images:
            args["image_id"] = str(images[-1].id)
        else:
            return args, "I need an image to edit. Generate a diagram first."

    if tool_name in {"render_image_from_plan", "edit_existing_image", "edit_diagram_ir"}:
        # Always force-set session_id; planner may supply placeholder strings
        args["session_id"] = str(session.id)

    if tool_name == "edit_diagram_ir":
        # Inject the latest IR id when the planner-supplied ir_id is missing or
        # looks like a placeholder that won't resolve in the DB.
        supplied_ir_id = args.get("ir_id")
        if not supplied_ir_id or supplied_ir_id == "session_id_placeholder":
            ir_versions = list_ir_versions(db, session.id)
            if ir_versions:
                args["ir_id"] = str(ir_versions[-1].id)
            else:
                args.pop("ir_id", None)

    return args, None


def _record_plan_execution(
    db: DbSession,
    plan_record: PlanRecord,
    step_index: int,
    tool_name: str,
    arguments: dict,
    output: dict | None,
    audit_id: str | None,
    duration_ms: int,
) -> PlanExecution:
    exec_record = PlanExecution(
        plan_id=plan_record.id,
        step_index=step_index,
        tool_name=tool_name,
        arguments=arguments,
        output=output,
        audit_id=_parse_uuid(audit_id) if audit_id else None,
        duration_ms=duration_ms,
    )
    db.add(exec_record)
    return exec_record


def _handle_llm_diagram_step(
    db: DbSession,
    session: Session,
    plan_record: PlanRecord,
    *,
    llm_payload: dict,
    diagram_type: str | None,
    user_prompt: str,
    plan_data: Dict[str, Any] | None,
) -> dict:
    if not llm_payload:
        raise ValueError("Missing llm_diagram payload for rendering step")
    diagram_text = llm_payload.get("diagram") or llm_payload.get("text")
    if not diagram_text:
        raise ValueError("Diagram payload is empty")
    fmt_token = (llm_payload.get("format") or "plantuml").lower()
    if fmt_token.startswith("plant"):
        fmt = "plantuml"
    elif fmt_token.startswith("mermaid"):
        fmt = "mermaid"
    else:
        raise ValueError(f"Unsupported diagram format '{llm_payload.get('format')}'")

    target_type = (diagram_type or "diagram").replace(" ", "_")
    version_seed = _next_version(db, session.id)
    output_name = f"{session.id}_{target_type}_{version_seed}"

    if fmt == "plantuml":
        render_payload = render_llm_plantuml(diagram_text, output_name, diagram_type=target_type)
        svg_text = read_text_file(render_payload["file_path"])
    else:
        render_payload = render_llm_mermaid(diagram_text, output_name)
        svg_text = render_payload["svg_text"]

    metadata_payload = _metadata_from_plan_or_default(plan_data, target_type) if plan_data else None
    if metadata_payload:
        svg_text = _ensure_ir_metadata(svg_text, metadata_payload)

    ir_payload: Dict[str, Any] = {"source": "llm", "format": fmt, "rendering_service": f"llm_{fmt}"}
    if metadata_payload:
        ir_payload["enriched_ir"] = metadata_payload

    ir_version = _create_ir_version(
        db,
        session,
        diagram_type=target_type,
        svg_text=svg_text,
        reason="llm diagram",
        parent_ir_id=None,
        ir_json=ir_payload,
        plantuml_text=render_payload.get("sanitized_text") if fmt == "plantuml" else None,
    )
    created_image = _create_image(
        db,
        session,
        file_path=render_payload["file_path"],
        prompt=None,
        reason=f"llm diagram: {target_type}",
        ir_id=ir_version.id,
    )

    audit = record_styling_audit(
        db,
        session_id=session.id,
        plan_id=plan_record.id,
        diagram_id=created_image.id,
        diagram_type=target_type,
        user_prompt=user_prompt,
        llm_format=fmt,
        llm_diagram=diagram_text,
        sanitized_diagram=render_payload.get("sanitized_text"),
        extracted_intent=None,
        styling_plan=None,
        execution_steps=[f"Validated {fmt} diagram provided by planner."],
        agent_reasoning=None,
        mode="post-svg",
        renderer_input_before=diagram_text,
        renderer_input_after=render_payload.get("sanitized_text"),
        svg_before=None,
        svg_after=svg_text,
        validation_warnings=render_payload.get("warnings"),
        blocked_tokens=None,
    )

    return {
        "image": created_image,
        "ir_version": ir_version,
        "audit_id": str(audit.id),
        "diagram_type": target_type,
        "warnings": render_payload.get("warnings", []),
        "format": fmt,
        "schema_version": llm_payload.get("schema_version") or 1,
    }


def handle_message(db: DbSession, session: Session, message: str) -> dict:
    db.add(
        Message(
            session_id=session.id,
            role="user",
            content=message,
            message_type="text",
        )
    )
    db.commit()

    if not mcp_registry.get_tool("generate_architecture_plan"):
        register_mcp_tools(mcp_registry)

    planner = ConversationPlannerAgent()
    state, context_cache = _build_planner_context(db, session)
    last_image_id: UUID | None = None
    generated_image_ids: List[UUID] = []
    existing_images = context_cache.get("images", []) or []
    if existing_images:
        last_image_id = existing_images[-1].id

    latest_plan_record: ArchitecturePlanRecord | None = context_cache.get("latest_plan")
    latest_plan_data: Dict[str, Any] | None = None
    if latest_plan_record and isinstance(latest_plan_record.data, dict):
        latest_plan_data = latest_plan_record.data
    metadata_cache: Dict[str, Dict[str, Any]] = {}

    logger.info(
        "Planning session message",
        extra={
            "session_id": str(session.id),
            "image_count": len(context_cache.get("images", [])),
            "diagram_count": len(context_cache.get("diagrams", [])),
            "has_plan": bool(context_cache.get("latest_plan")),
        },
    )

    planner_start = time.perf_counter()
    plan_result = planner.plan(message, state, mcp_registry.list_tools())
    planner_ms = int((time.perf_counter() - planner_start) * 1000)
    intent = plan_result.get("intent", "clarify")
    plan_id_value = plan_result.get("plan_id") or str(uuid4())
    plan_uuid = _parse_uuid(plan_id_value)

    logger.info(
        "Planner produced plan",
        extra={
            "session_id": str(session.id),
            "plan_id": plan_id_value,
            "intent": intent,
            "step_count": len(plan_result.get("plan", []) or []),
        },
    )

    # ── Trace: planner decision ──
    planner_meta = plan_result.get("metadata") if isinstance(plan_result.get("metadata"), dict) else {}
    record_trace(
        db,
        session_id=session.id,
        agent_name="conversation_planner",
        input_summary={
            "user_message": message,
            "has_plan": bool(context_cache.get("latest_plan")),
            "image_count": len(context_cache.get("images", []) or []),
            "active_image_id": state.get("active_image_id"),
        },
        output_summary={
            "intent": intent,
            "steps": [
                {"tool": s.get("tool"), "diagram_type": s.get("diagram_type")}
                for s in (plan_result.get("plan") or [])
            ],
            "source": planner_meta.get("source"),
            "model": planner_meta.get("model"),
        },
        decision=f"intent={intent}, steps={len(plan_result.get('plan') or [])}",
        reasoning=planner_meta.get("raw_response") if isinstance(planner_meta, dict) else None,
        plan_id=plan_uuid,
        duration_ms=planner_ms,
    )

    metadata_payload = plan_result.get("metadata") if isinstance(plan_result.get("metadata"), dict) else {}
    metadata_payload = dict(metadata_payload)
    metadata_payload["user_message"] = message

    plan_record = PlanRecord(
        id=plan_uuid,
        session_id=session.id,
        intent=intent,
        plan_json=plan_result.get("plan", []),
        metadata_json=metadata_payload,
        executed=False,
    )
    db.add(plan_record)
    db.commit()

    tool_results: list[dict] = []
    assistant_messages: list[Message] = []
    response_text: str | None = None
    result_payload: dict = {}
    created_image: Image | None = None
    error_occurred = False

    for step_index, step in enumerate(plan_result.get("plan", []) or []):
        tool_name = step.get("tool")
        rendering_service = (step.get("rendering_service") or "").lower()
        llm_payload_raw = step.get("llm_diagram")
        llm_payload = None
        if isinstance(llm_payload_raw, str):
            try:
                llm_payload = json.loads(llm_payload_raw)
            except json.JSONDecodeError:
                llm_payload = None
            if llm_payload is None:
                fmt_hint = (step.get("format") or step.get("diagram_format") or "").lower()
                if fmt_hint.startswith("plant") or fmt_hint.startswith("mermaid"):
                    llm_payload = {"format": fmt_hint, "diagram": llm_payload_raw, "schema_version": 1}
        elif isinstance(llm_payload_raw, dict):
            llm_payload = llm_payload_raw
        if rendering_service in {"llm_plantuml", "llm_mermaid"} or llm_payload:
            if not llm_payload:
                response_text = "Planner selected LLM rendering but omitted llm_diagram payload."
                error_occurred = True
                break
            start = time.perf_counter()
            try:
                llm_result = _handle_llm_diagram_step(
                    db,
                    session,
                    plan_record,
                    llm_payload=llm_payload,
                    diagram_type=step.get("diagram_type"),
                    user_prompt=message,
                    plan_data=latest_plan_data,
                )
            except DiagramValidationError as exc:
                duration_ms = int((time.perf_counter() - start) * 1000)
                blocked = ", ".join(exc.result.blocked_tokens) if getattr(exc, "result", None) else ""
                response_text = f"Rejected diagram from planner: {exc}. {blocked}".strip()
                record_trace(
                    db,
                    session_id=session.id,
                    agent_name="llm.diagram",
                    input_summary={"rendering_service": rendering_service},
                    output_summary=None,
                    decision="validation_rejected",
                    plan_id=plan_record.id,
                    step_index=step_index,
                    duration_ms=duration_ms,
                    error=response_text,
                )
                error_occurred = True
                break
            except Exception as exc:
                duration_ms = int((time.perf_counter() - start) * 1000)
                logger.exception(
                    "Failed to render LLM diagram",
                    extra={"session_id": str(session.id), "plan_id": str(plan_record.id)},
                )
                response_text = f"Unable to render provided diagram: {exc}"
                record_trace(
                    db,
                    session_id=session.id,
                    agent_name="llm.diagram",
                    input_summary={"rendering_service": rendering_service},
                    output_summary=None,
                    decision="error",
                    plan_id=plan_record.id,
                    step_index=step_index,
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                error_occurred = True
                break

            duration_ms = int((time.perf_counter() - start) * 1000)
            assistant_messages.append(
                Message(
                    session_id=session.id,
                    role="assistant",
                    content="",
                    intent=intent,
                    image_id=llm_result["image"].id,
                    message_type="image",
                    image_version=llm_result["image"].version,
                    diagram_type=llm_result["diagram_type"],
                    ir_id=llm_result["ir_version"].id,
                )
            )
            last_image_id = llm_result["image"].id
            exec_record = _record_plan_execution(
                db,
                plan_record,
                step_index,
                "llm.diagram",
                {
                    "format": llm_result["format"],
                    "diagram_type": llm_result["diagram_type"],
                    "rendering_service": rendering_service or f"llm_{llm_result['format']}",
                },
                {"image_id": str(llm_result["image"].id)},
                llm_result["audit_id"],
                duration_ms,
            )
            tool_results.append({
                "tool": "llm.diagram",
                "rendering_service": rendering_service or f"llm_{llm_result['format']}",
                "output": {"image_id": str(llm_result["image"].id), "audit_id": llm_result["audit_id"]},
                "audit_id": llm_result["audit_id"],
                "execution_id": str(exec_record.id),
            })

            # ── Trace: LLM diagram step ──
            record_trace(
                db,
                session_id=session.id,
                agent_name="llm.diagram",
                input_summary={
                    "format": llm_result["format"],
                    "diagram_type": llm_result["diagram_type"],
                    "rendering_service": rendering_service or f"llm_{llm_result['format']}",
                    "user_prompt_len": len(message) if message else 0,
                },
                output_summary={
                    "image_id": str(llm_result["image"].id),
                    "audit_id": llm_result["audit_id"],
                },
                decision=f"rendered {llm_result['format']} {llm_result['diagram_type']}",
                plan_id=plan_record.id,
                step_index=step_index,
                duration_ms=duration_ms,
            )
            generated_image_ids.append(llm_result["image"].id)
            continue
        if not tool_name:
            continue
        args, prep_error = _prepare_tool_arguments(db, session, plan_result, tool_name, step.get("arguments", {}), message)
        if prep_error:
            response_text = prep_error
            error_occurred = True
            break
        args = dict(args)
        execution_args_list: List[Dict[str, Any]] = [args]
        styled_target_ids: list[str] = []

        if tool_name == "styling.apply_post_svg":
            requested_id = args.get("diagramId")
            if requested_id == LATEST_IMAGE_PLACEHOLDER:
                if generated_image_ids:
                    execution_args_list = []
                    for image_id in generated_image_ids:
                        call_args = dict(args)
                        call_args["diagramId"] = str(image_id)
                        execution_args_list.append(call_args)
                        styled_target_ids.append(str(image_id))
                elif last_image_id:
                    args["diagramId"] = str(last_image_id)
                    styled_target_ids = [str(last_image_id)]
                else:
                    response_text = "I need an existing diagram before I can apply that styling."
                    error_occurred = True
                    break
            elif requested_id:
                styled_target_ids = [str(requested_id)]
            else:
                response_text = "I need an existing diagram before I can apply that styling."
                error_occurred = True
                break

        exec_context = {
            "db": db,
            "session": session,
            "session_id": str(session.id),
            "user_message": message,
            "plan_id": str(plan_record.id),
        }

        for call_args in execution_args_list:
            logger.info(
                "Executing MCP tool",
                extra={
                    "session_id": str(session.id),
                    "plan_id": plan_id_value,
                    "tool": tool_name,
                    "step_index": step_index,
                },
            )
            start = time.perf_counter()
            try:
                tool_output = mcp_registry.execute(tool_name, call_args, context=exec_context)
            except Exception as exc:
                duration_ms = int((time.perf_counter() - start) * 1000)
                logger.exception(
                    "MCP tool failed",
                    extra={"session_id": str(session.id), "plan_id": plan_id_value, "tool": tool_name},
                )
                _record_plan_execution(
                    db,
                    plan_record,
                    step_index,
                    tool_name,
                    call_args,
                    {"error": str(exc)},
                    None,
                    duration_ms,
                )
                record_trace(
                    db,
                    session_id=session.id,
                    agent_name=f"tool.{tool_name}",
                    input_summary={k: v for k, v in call_args.items() if k not in ("architecture_plan",)},
                    output_summary=None,
                    decision="error",
                    plan_id=plan_record.id,
                    step_index=step_index,
                    duration_ms=duration_ms,
                    error=str(exc),
                )
                response_text = f"Tool '{tool_name}' failed: {exc}"
                error_occurred = True
                break
            duration_ms = int((time.perf_counter() - start) * 1000)
            audit_id = tool_output.get("audit_id") or tool_output.get("auditId")
            logger.info(
                "MCP tool completed",
                extra={
                    "session_id": str(session.id),
                    "plan_id": plan_id_value,
                    "tool": tool_name,
                    "audit_id": audit_id,
                    "duration_ms": duration_ms,
                },
            )
            _record_plan_execution(db, plan_record, step_index, tool_name, call_args, tool_output, audit_id, duration_ms)
            tool_results.append({"tool": tool_name, "output": tool_output})

            # ── Trace: tool execution ──
            _tool_out_summary = {}
            for _tk, _tv in (tool_output or {}).items():
                if _tk in ("svg", "svg_text", "plantuml_text", "architecture_plan"):
                    _tool_out_summary[_tk] = f"<{len(str(_tv))} chars>" if _tv else None
                elif _tk == "ir_entries":
                    _tool_out_summary[_tk] = [
                        {ek: (f"<{len(str(ev))} chars>" if ek in ("svg",) and ev else ev)
                         for ek, ev in (e or {}).items()}
                        for e in (_tv or [])
                    ]
                else:
                    _tool_out_summary[_tk] = _tv
            _tool_in_summary = {k: v for k, v in call_args.items() if k not in ("architecture_plan",)}
            if "architecture_plan" in call_args:
                _tool_in_summary["architecture_plan"] = "<present>"
            record_trace(
                db,
                session_id=session.id,
                agent_name=f"tool.{tool_name}",
                input_summary=_tool_in_summary,
                output_summary=_tool_out_summary,
                decision=f"completed in {duration_ms}ms",
                plan_id=plan_record.id,
                step_index=step_index,
                duration_ms=duration_ms,
            )

            if tool_name == "generate_architecture_plan":
                plan_data = tool_output.get("architecture_plan")
                if plan_data:
                    latest_record = ArchitecturePlanRecord(session_id=session.id, data=plan_data)
                    db.add(latest_record)
                    db.flush()
                    context_cache["latest_plan"] = latest_record
                    latest_plan_record = latest_record
                    latest_plan_data = plan_data if isinstance(plan_data, dict) else None
                    metadata_cache.clear()
            elif tool_name in {
                "generate_plantuml",
                "generate_diagram",
                "generate_multiple_diagrams",  # kept for backwards compat if still referenced
                "edit_diagram_via_semantic_understanding",
                "edit_diagram_ir",
                "generate_sequence_from_architecture",
                "generate_plantuml_sequence",
            }:
                for entry in tool_output.get("ir_entries", []) or []:
                    # Allow styling transform entries that contain patch_ops or updated_ir
                    if entry.get("patch_ops") or entry.get("updated_ir"):
                        # Main Agent deterministic application of styling patches/updates
                        parent_ir_id = entry.get("parent_ir_id")
                        diagram_type = entry.get("diagram_type") or "diagram"
                        # Resolve parent IR
                        parent_ir = None
                        if parent_ir_id:
                            try:
                                parent_ir = db.get(DiagramIR, _parse_uuid(parent_ir_id))
                            except Exception:
                                parent_ir = None
                        if not parent_ir:
                            # fallback to latest
                            parent_ir = db.execute(
                                select(DiagramIR).where(DiagramIR.session_id == session.id).order_by(DiagramIR.version.desc())
                            ).scalars().first()

                        parent_ir_json = dict(parent_ir.ir_json) if parent_ir and parent_ir.ir_json else {}

                        # Apply patch_ops deterministically if provided
                        updated_ir_json = None
                        if entry.get("patch_ops"):
                            try:
                                updated_ir_json = _apply_patch_ops_to_ir(parent_ir_json, entry.get("patch_ops"))
                            except Exception as exc:
                                logger.exception("Patch application failed", extra={"session_id": str(session.id), "error": str(exc)})
                                # Record audit via styling_audit and continue safely
                                record_styling_audit(
                                    db,
                                    session_id=session.id,
                                    plan_id=plan_id_value,
                                    diagram_id=None,
                                    diagram_type=diagram_type,
                                    user_prompt=None,
                                    llm_format=None,
                                    llm_diagram=None,
                                    extracted_intent=None,
                                    styling_plan=None,
                                    execution_steps=["patch_apply_failed"],
                                    agent_reasoning=str(exc),
                                    mode="patch_apply_failed",
                                    renderer_input_before=None,
                                    renderer_input_after=None,
                                    svg_before=None,
                                    svg_after=None,
                                )
                                continue
                        elif entry.get("updated_ir"):
                            updated_ir_json = entry.get("updated_ir")

                        if updated_ir_json is None:
                            continue

                        # Create new IR version with updated_ir_json, reuse svg if provided or parent svg
                        svg_text = entry.get("svg") or (parent_ir.svg_text if parent_ir else "")

                        # ── Apply per-node style changes from the patched IR ──
                        # The IR carries node_style (fillColor, borderColor, etc.)
                        # per node.  We must project those onto the SVG elements
                        # so the visual output actually reflects the edit.
                        if isinstance(updated_ir_json, dict):
                            svg_text = apply_ir_node_styles_to_svg(svg_text, updated_ir_json)

                        # Ensure metadata embedding — use the full patched IR so
                        # the SVG metadata stays in sync with the authoritative IR.
                        metadata_for_svg = updated_ir_json if isinstance(updated_ir_json, dict) else {}
                        svg_text = _ensure_ir_metadata(svg_text, metadata_for_svg)

                        ir_version = _create_ir_version(
                            db,
                            session,
                            diagram_type=diagram_type,
                            svg_text=svg_text,
                            reason=entry.get("reason") or "styling_patch",
                            parent_ir_id=parent_ir.id if parent_ir else None,
                            ir_json=updated_ir_json,
                        )

                        svg_file = render_ir_svg(svg_text, f"{session.id}_{diagram_type}_{ir_version.version}")
                        created_image = _create_image(
                            db,
                            session,
                            file_path=svg_file,
                            prompt=None,
                            reason=f"diagram: {diagram_type}",
                            ir_id=ir_version.id,
                        )
                        assistant_messages.append(
                            Message(
                                session_id=session.id,
                                role="assistant",
                                content="",
                                intent=intent,
                                image_id=created_image.id,
                                message_type="image",
                                image_version=created_image.version,
                                diagram_type=diagram_type,
                                ir_id=ir_version.id,
                            )
                        )
                        last_image_id = created_image.id
                        generated_image_ids.append(created_image.id)

                        # ── Trace: patch / IR update application ──
                        _patch_input = {
                            "parent_ir_id": str(parent_ir_id) if parent_ir_id else None,
                            "diagram_type": diagram_type,
                            "has_patch_ops": bool(entry.get("patch_ops")),
                            "has_updated_ir": bool(entry.get("updated_ir")),
                        }
                        if entry.get("patch_ops"):
                            _patch_input["patch_ops_count"] = len(entry["patch_ops"])
                        record_trace(
                            db,
                            session_id=session.id,
                            agent_name="patch.apply_ir",
                            input_summary=_patch_input,
                            output_summary={
                                "image_id": str(created_image.id),
                                "ir_version_id": str(ir_version.id),
                                "ir_version": ir_version.version,
                            },
                            decision=f"applied {'patch_ops' if entry.get('patch_ops') else 'updated_ir'} → {diagram_type}",
                            plan_id=plan_record.id,
                            step_index=step_index,
                        )
                        continue

                    diagram_type = entry.get("diagram_type") or "diagram"
                    svg_text = entry.get("svg")
                    svg_file = entry.get("svg_file")
                    parent_ir_id = entry.get("parent_ir_id")
                    if not svg_text:
                        continue
                    semantic_intent = None
                    try:
                        semantic_intent, _ = generate_semantic_intent(svg_text, message)
                    except Exception:
                        logger.exception(
                            "Failed to derive semantic intent",
                            extra={
                                "session_id": str(session.id),
                                "plan_id": plan_id_value,
                                "tool": tool_name,
                                "diagram_type": diagram_type,
                            },
                        )
                    metadata_payload = metadata_cache.get(diagram_type)
                    if metadata_payload is None:
                        metadata_payload = _metadata_from_plan_or_default(latest_plan_data, diagram_type)
                        metadata_cache[diagram_type] = metadata_payload
                    svg_text = _ensure_ir_metadata(svg_text, metadata_payload)
                    ir_payload: Dict[str, Any] = {"intent": diagram_type}
                    rendering_service = entry.get("rendering_service")
                    if rendering_service:
                        ir_payload["rendering_service"] = rendering_service
                    if metadata_payload:
                        ir_payload["enriched_ir"] = metadata_payload
                    ir_version = _create_ir_version(
                        db,
                        session,
                        diagram_type=diagram_type,
                        svg_text=svg_text,
                        reason=entry.get("reason") or intent,
                        parent_ir_id=_parse_uuid(parent_ir_id) if parent_ir_id else None,
                        ir_json=ir_payload,
                        semantic_intent=semantic_intent,
                    )
                    if not svg_file:
                        svg_file = render_ir_svg(svg_text, f"{session.id}_{diagram_type}_{ir_version.version}")
                    created_image = _create_image(
                        db,
                        session,
                        file_path=svg_file,
                        prompt=None,
                        reason=f"diagram: {diagram_type}",
                        ir_id=ir_version.id,
                    )
                    assistant_messages.append(
                        Message(
                            session_id=session.id,
                            role="assistant",
                            content="",
                            intent=intent,
                            image_id=created_image.id,
                            message_type="image",
                            image_version=created_image.version,
                            diagram_type=diagram_type,
                            ir_id=ir_version.id,
                        )
                    )
                    last_image_id = created_image.id
                    generated_image_ids.append(created_image.id)
            elif tool_name in {"render_image_from_plan", "edit_existing_image"}:
                image_file = tool_output.get("image_file")
                if image_file:
                    created_image = _create_image(
                        db,
                        session,
                        file_path=image_file,
                        prompt=tool_output.get("prompt"),
                        reason="edit" if tool_name == "edit_existing_image" else "generate",
                    )
                    diagram_type = _infer_diagram_type(image_file)
                    assistant_messages.append(
                        Message(
                            session_id=session.id,
                            role="assistant",
                            content="",
                            intent=intent,
                            image_id=created_image.id,
                            message_type="image",
                            image_version=created_image.version,
                            diagram_type=diagram_type,
                        )
                    )
                    last_image_id = created_image.id
            elif tool_name == "styling.apply_post_svg":
                svg_after = tool_output.get("svgAfter") or tool_output.get("svg")
                diagram_id_value = call_args.get("diagramId")
                image_record = None
                if diagram_id_value:
                    try:
                        image_record = db.get(Image, _parse_uuid(diagram_id_value))
                    except (TypeError, ValueError):
                        image_record = None
                if svg_after and image_record:
                    diagram_type = _infer_diagram_type(image_record.file_path)
                    parent_ir = db.get(DiagramIR, image_record.ir_id) if getattr(image_record, "ir_id", None) else None
                    inherited_ir_json = dict(parent_ir.ir_json) if parent_ir and parent_ir.ir_json else None
                    semantic_intent = None
                    intent_payload = None
                    if parent_ir and parent_ir.ir_json:
                        intent_payload = parent_ir.ir_json.get("aesthetic_intent")
                    if intent_payload:
                        try:
                            semantic_intent = SemanticAestheticIR.from_dict(intent_payload)
                        except Exception:
                            logger.exception(
                                "Failed to hydrate semantic intent from parent IR",
                                extra={"session_id": str(session.id), "diagram_type": diagram_type},
                            )
                    ir_version = _create_ir_version(
                        db,
                        session,
                        diagram_type=diagram_type,
                        svg_text=svg_after,
                        reason="styling",
                        parent_ir_id=image_record.ir_id,
                        ir_json=inherited_ir_json,
                        semantic_intent=semantic_intent,
                    )
                    svg_file = render_ir_svg(svg_after, f"{session.id}_{diagram_type}_{ir_version.version}")
                    styled_image = _create_image(
                        db,
                        session,
                        file_path=svg_file,
                        prompt=None,
                        reason="styling",
                        parent_image_id=image_record.id,
                        ir_id=ir_version.id,
                    )
                    assistant_messages.append(
                        Message(
                            session_id=session.id,
                            role="assistant",
                            content="",
                            intent=intent,
                            image_id=styled_image.id,
                            message_type="image",
                            image_version=styled_image.version,
                            diagram_type=diagram_type,
                            ir_id=ir_version.id,
                        )
                    )
                    last_image_id = styled_image.id
            elif tool_name == "explain_architecture":
                response_text = tool_output.get("answer") or ""
                result_payload["explanation"] = response_text

            if error_occurred:
                break

        if error_occurred:
            break

        if tool_name == "styling.apply_post_svg" and styled_target_ids:
            generated_image_ids[:] = [img for img in generated_image_ids if str(img) not in styled_target_ids]

    if not error_occurred:
        plan_record.executed = True

    if not tool_results and intent == "diagram_change":
        target_type = plan_result.get("target_diagram_type")
        ir_versions = list_ir_versions(db, session.id)
        latest_by_type: dict[str, DiagramIR] = {ir.diagram_type: ir for ir in ir_versions}
        if target_type in latest_by_type:
            ir_version = latest_by_type[target_type]
            svg_file = render_ir_svg(ir_version.svg_text, f"{session.id}_{target_type}_{ir_version.version}")
            created_image = _create_image(
                db,
                session,
                file_path=svg_file,
                prompt=None,
                reason=f"diagram change: {target_type}",
                ir_id=ir_version.id,
            )
            assistant_messages.append(
                Message(
                    session_id=session.id,
                    role="assistant",
                    content="",
                    intent=intent,
                    image_id=created_image.id,
                    message_type="image",
                    image_version=created_image.version,
                    diagram_type=target_type,
                    ir_id=ir_version.id,
                )
            )
            result_payload["diagram_type"] = target_type
            response_text = ""
        elif plan_result.get("requires_regeneration"):
            if session.input_text:
                ingest_input(db, session, files=None, text=session.input_text)
                result_payload["diagram_type"] = target_type
                response_text = "Regenerated architecture to include requested diagram."
            else:
                response_text = "I need the original input (file or text) to regenerate. Please re-upload or paste it."
        else:
            response_text = response_text or "Requested diagram type not available."

    if response_text is None:
        if assistant_messages:
            diagram_types = sorted({msg.diagram_type for msg in assistant_messages if msg.diagram_type})
            if diagram_types:
                response_text = f"Generated {', '.join(diagram_types)} diagram(s)."
            else:
                response_text = ""
        elif result_payload.get("explanation"):
            response_text = result_payload.get("explanation") or ""
        else:
            response_text = plan_result.get("instructions") or "Done."

    if response_text:
        db.add(
            Message(
                session_id=session.id,
                role="assistant",
                content=response_text,
                intent=intent,
                image_id=None if assistant_messages else (created_image.id if created_image else None),
                message_type="text",
                image_version=None if assistant_messages else (created_image.version if created_image else None),
                diagram_type=None if assistant_messages else (_infer_diagram_type(created_image.file_path) if created_image else None),
            )
        )

    for msg in assistant_messages:
        db.add(msg)

    db.commit()

    return {
        "intent": intent,
        "response": response_text,
        "result": result_payload,
        "plan": plan_result,
        "plan_id": str(plan_record.id),
        "tool_results": tool_results,
    }


def get_plan_with_history(db: DbSession, plan_id: UUID | str) -> tuple[PlanRecord | None, list[PlanExecution]]:
    try:
        plan_uuid = _parse_uuid(plan_id)
    except (TypeError, ValueError):
        return None, []
    plan = db.get(PlanRecord, plan_uuid)
    if not plan:
        return None, []
    executions = list(
        db.execute(
            select(PlanExecution).where(PlanExecution.plan_id == plan_uuid).order_by(PlanExecution.created_at)
        ).scalars()
    )
    return plan, executions


def _create_image(
    db: DbSession,
    session: Session,
    file_path: str,
    prompt: str | None,
    reason: str,
    parent_image_id: UUID | None = None,
    ir_id: UUID | None = None,
) -> Image:
    last = db.execute(
        select(Image).where(Image.session_id == session.id).order_by(Image.version.desc())
    ).scalars().first()
    image = Image(
        session_id=session.id,
        version=(last.version + 1) if last else 1,
        parent_image_id=parent_image_id or (last.id if last else None),
        file_path=file_path,
        prompt=prompt,
        reason=reason,
        source_repo=session.source_repo,
        source_commit=session.source_commit,
        ir_id=ir_id,
    )
    db.add(image)
    db.flush()
    return image


def _next_version(db: DbSession, session_id: UUID) -> int:
    last = db.execute(
        select(Image).where(Image.session_id == session_id).order_by(Image.version.desc())
    ).scalars().first()
    return (last.version + 1) if last else 1


def _create_ir_version(
    db: DbSession,
    session: Session,
    diagram_type: str,
    svg_text: str,
    reason: str,
    parent_ir_id: UUID | None = None,
    ir_json: dict | None = None,
    plantuml_text: str | None = None,
    semantic_intent: SemanticAestheticIR | None = None,
) -> DiagramIR:
    last = db.execute(
        select(DiagramIR).where(DiagramIR.session_id == session.id).order_by(DiagramIR.version.desc())
    ).scalars().first()
    if svg_text is None:
        logging.getLogger(__name__).warning("Creating IR version with empty svg_text for session %s diagram %s", session.id, diagram_type)
        svg_text = ""

    payload = dict(ir_json or {})
    if semantic_intent:
        try:
            payload["aesthetic_intent"] = semantic_intent.to_dict()
        except Exception:
            logging.getLogger(__name__).exception("Failed to serialize semantic intent for diagram %s", diagram_type)
    payload = payload or None

    ir_version = DiagramIR(
        session_id=session.id,
        diagram_type=diagram_type,
        version=(last.version + 1) if last else 1,
        parent_ir_id=parent_ir_id,
        reason=reason,
        svg_text=svg_text,
        ir_json=payload,
        plantuml_text=plantuml_text,
    )
    db.add(ir_version)
    db.flush()
    return ir_version


def _apply_patch_ops_to_ir(ir_json: dict, patch_ops: list[dict]) -> dict:
    import copy

    if not isinstance(ir_json, dict):
        raise ValueError("ir_json must be a dict to apply patches")
    working = copy.deepcopy(ir_json)

    allowed_prefixes = ("/nodes/", "/edges/", "/zone_order", "/globalIntent")

    def _find_node_by_id_or_label(nodes: list, node_id_or_label: str):
        for n in nodes:
            if str(n.get("node_id") or n.get("id") or "").lower() == node_id_or_label.lower():
                return n
            if str(n.get("label") or "").lower() == node_id_or_label.lower():
                return n
        return None

    nodes = working.setdefault("nodes", [])
    edges = working.setdefault("edges", [])

    # Navigate into enriched_ir when nodes/edges are nested (real DB IR structure)
    _inner = working.get("enriched_ir") if isinstance(working.get("enriched_ir"), dict) else None
    if _inner is not None:
        if not working.get("nodes") and _inner.get("nodes"):
            nodes = _inner["nodes"]
        if not working.get("edges") and _inner.get("edges"):
            edges = _inner["edges"]

    for op in patch_ops:
        if not isinstance(op, dict):
            raise ValueError("Invalid patch op format")
        path = op.get("path")
        if not path or not any(path.startswith(p) for p in allowed_prefixes):
            raise ValueError(f"Patch path not allowed: {path}")
        verb = op.get("op")
        value = op.get("value")

        # nodes path
        if path.startswith("/nodes/"):
            parts = path.split("/")
            # ['', 'nodes', '<node_id>', ...]
            if len(parts) < 4:
                raise ValueError(f"Invalid node patch path: {path}")
            node_key = parts[2]
            subpath = parts[3:]
            node = _find_node_by_id_or_label(nodes, node_key)
            if node is None:
                raise ValueError(f"Node not found for patch: {node_key}")
            # apply replace for known subpaths
            if len(subpath) == 1:
                field = subpath[0]
                if verb == "replace":
                    node[field] = value
                else:
                    raise ValueError(f"Unsupported op {verb} for node field")
            elif len(subpath) >= 2:
                # support node_style subfields
                if subpath[0] == "node_style":
                    style = node.setdefault("node_style", {})
                    field = subpath[1]
                    if verb == "replace":
                        style[field] = value
                    else:
                        raise ValueError(f"Unsupported op {verb} for node_style")
                else:
                    raise ValueError(f"Unsupported node subpath: {'/'.join(subpath)}")

        elif path.startswith("/edges/"):
            parts = path.split("/")
            if len(parts) < 4:
                raise ValueError(f"Invalid edge patch path: {path}")
            edge_key = parts[2]
            subpath = parts[3:]
            # find edge by edge_id
            target_edge = None
            for e in edges:
                if str(e.get("edge_id") or "").lower() == edge_key.lower():
                    target_edge = e
                    break
            if not target_edge:
                raise ValueError(f"Edge not found for patch: {edge_key}")
            if len(subpath) == 1:
                field = subpath[0]
                if verb == "replace":
                    target_edge[field] = value
                else:
                    raise ValueError(f"Unsupported op {verb} for edge field")
            else:
                raise ValueError("Unsupported edge subpath")
        elif path.startswith("/zone_order"):
            if verb == "replace":
                # Write zone_order into enriched_ir when the wrapper structure is present
                if _inner is not None:
                    _inner["zone_order"] = value
                else:
                    working["zone_order"] = value
            else:
                raise ValueError(f"Unsupported op {verb} for zone_order")
        elif path.startswith("/globalIntent"):
            parts = path.split("/")
            if len(parts) < 2:
                raise ValueError(f"Invalid globalIntent path: {path}")
            field_parts = parts[2:]
            gi = working.setdefault("globalIntent", {})
            if len(field_parts) == 1 and verb == "replace":
                gi[field_parts[0]] = value
            elif len(field_parts) >= 2 and verb == "replace":
                # nested fields
                cur = gi
                for p in field_parts[:-1]:
                    cur = cur.setdefault(p, {})
                cur[field_parts[-1]] = value
            else:
                raise ValueError(f"Unsupported op {verb} for globalIntent")
        else:
            raise ValueError(f"Unsupported patch path: {path}")

    # Structural validation
    node_ids = {str(n.get("node_id") or n.get("id") or "") for n in nodes if n.get("node_id") or n.get("id")}
    if len(node_ids) != len([n for n in nodes if n.get("node_id") or n.get("id")]):
        raise ValueError("Duplicate node ids introduced")

    for e in edges:
        from_id = e.get("from_id") or e.get("from") or e.get("source")
        to_id = e.get("to_id") or e.get("to") or e.get("target")
        if from_id and str(from_id) not in node_ids:
            raise ValueError(f"Orphan edge source: {from_id}")
        if to_id and str(to_id) not in node_ids:
            raise ValueError(f"Orphan edge target: {to_id}")

    return working


def _parse_uuid(value: str) -> UUID:
    return UUID(str(value))


def _infer_diagram_type(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    parts = name.split("_")
    if len(parts) >= 3:
        return parts[-2]
    return "diagram"
