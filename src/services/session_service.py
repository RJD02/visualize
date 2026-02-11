"""Session and conversation orchestration service."""
from __future__ import annotations

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
from src.mcp.tools import register_mcp_tools
from src.orchestrator.adk_workflow import ADKWorkflow
from src.services.intent import explain_architecture
from src.services.styling_audit_service import record_styling_audit
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

                svg_text = _ensure_ir_metadata(svg_text, _diagram_metadata_payload(diagram_type))
                
                ir_version = _create_ir_version(
                    db,
                    session,
                    diagram_type=diagram_type,
                    svg_text=svg_text,
                    reason="architecture intent",
                    parent_ir_id=None,
                    ir_json={"intent": diagram_type},
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
        "generate_multiple_diagrams",
        "edit_diagram_via_semantic_understanding",
    }:
        args.setdefault("output_name", f"{session.id}_{_next_version(db, session.id)}")

    if tool_name == "generate_multiple_diagrams":
        if "diagram_types" not in args and planned_types:
            if isinstance(diagram_count, int) and diagram_count > 0:
                args["diagram_types"] = planned_types[:diagram_count]
            else:
                args["diagram_types"] = planned_types
        if "diagram_types" not in args and isinstance(diagram_count, int) and diagram_count > 0:
            latest_plan = get_latest_plan(db, session.id)
            if latest_plan and isinstance(latest_plan.data, dict):
                types = latest_plan.data.get("diagram_views") or []
                if types:
                    args["diagram_types"] = list(types)[:diagram_count]

    if tool_name in {
        "generate_plantuml",
        "generate_diagram",
        "generate_multiple_diagrams",
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
        args.setdefault("session_id", str(session.id))

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

    ir_version = _create_ir_version(
        db,
        session,
        diagram_type=target_type,
        svg_text=svg_text,
        reason="llm diagram",
        parent_ir_id=None,
        ir_json={"source": "llm", "format": fmt},
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
        renderer_input_before=llm_diagram,
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
    existing_images = context_cache.get("images", []) or []
    if existing_images:
        last_image_id = existing_images[-1].id

    logger.info(
        "Planning session message",
        extra={
            "session_id": str(session.id),
            "image_count": len(context_cache.get("images", [])),
            "diagram_count": len(context_cache.get("diagrams", [])),
            "has_plan": bool(context_cache.get("latest_plan")),
        },
    )

    plan_result = planner.plan(message, state, mcp_registry.list_tools())
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
        if isinstance(llm_payload_raw, str):
            try:
                llm_payload = json.loads(llm_payload_raw)
            except json.JSONDecodeError:
                llm_payload = None
        elif isinstance(llm_payload_raw, dict):
            llm_payload = llm_payload_raw
        else:
            llm_payload = None
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
                )
            except DiagramValidationError as exc:
                blocked = ", ".join(exc.result.blocked_tokens) if getattr(exc, "result", None) else ""
                response_text = f"Rejected diagram from planner: {exc}. {blocked}".strip()
                error_occurred = True
                break
            except Exception as exc:
                logger.exception(
                    "Failed to render LLM diagram",
                    extra={"session_id": str(session.id), "plan_id": str(plan_record.id)},
                )
                response_text = f"Unable to render provided diagram: {exc}"
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
            continue
        if not tool_name:
            continue
        args, prep_error = _prepare_tool_arguments(db, session, plan_result, tool_name, step.get("arguments", {}), message)
        if prep_error:
            response_text = prep_error
            error_occurred = True
            break
        if args.get("diagramId") == LATEST_IMAGE_PLACEHOLDER:
            if last_image_id:
                args["diagramId"] = str(last_image_id)
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
            tool_output = mcp_registry.execute(tool_name, args, context=exec_context)
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
                args,
                {"error": str(exc)},
                None,
                duration_ms,
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
        _record_plan_execution(db, plan_record, step_index, tool_name, args, tool_output, audit_id, duration_ms)
        tool_results.append({"tool": tool_name, "output": tool_output})

        if tool_name == "generate_architecture_plan":
            plan_data = tool_output.get("architecture_plan")
            if plan_data:
                latest_record = ArchitecturePlanRecord(session_id=session.id, data=plan_data)
                db.add(latest_record)
                db.flush()
                context_cache["latest_plan"] = latest_record
        elif tool_name in {
            "generate_plantuml",
            "generate_diagram",
            "generate_multiple_diagrams",
            "edit_diagram_via_semantic_understanding",
            "edit_diagram_ir",
            "generate_sequence_from_architecture",
            "generate_plantuml_sequence",
        }:
            for entry in tool_output.get("ir_entries", []) or []:
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
                ir_version = _create_ir_version(
                    db,
                    session,
                    diagram_type=diagram_type,
                    svg_text=svg_text,
                    reason=entry.get("reason") or intent,
                    parent_ir_id=_parse_uuid(parent_ir_id) if parent_ir_id else None,
                    ir_json={"intent": diagram_type},
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
            diagram_id_value = args.get("diagramId")
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


def _parse_uuid(value: str) -> UUID:
    return UUID(str(value))


def _infer_diagram_type(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    parts = name.split("_")
    if len(parts) >= 3:
        return parts[-2]
    return "diagram"
