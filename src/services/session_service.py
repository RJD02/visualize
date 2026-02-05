"""Session and conversation orchestration service."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from src.db_models import ArchitecturePlan as ArchitecturePlanRecord, DiagramFile, DiagramIR, Image, Message, Session
from src.models.architecture_plan import ArchitecturePlan as ArchitecturePlanModel
from src.agents.conversation_planner_agent import ConversationPlannerAgent
from src.mcp.registry import mcp_registry
from src.mcp.tools import register_mcp_tools
from src.orchestrator.adk_workflow import ADKWorkflow
from src.services.intent import explain_architecture
from src.tools.file_storage import save_json
from src.tools.text_extractor import extract_text
from src.tools.svg_ir import generate_svg_from_plan, edit_ir_svg, render_ir_svg
from src.tools.plantuml_renderer import generate_plantuml_from_plan, render_diagrams
from src.utils.config import settings
from src.intent.semantic_intent_llm import generate_semantic_intent
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


def save_edited_ir(db: DbSession, image_id: str, svg_text: str, reason: str = "edited via ui") -> Image:
    image = db.get(Image, image_id)
    if not image:
        raise ValueError("Image not found")
    session = db.get(Session, image.session_id)
    if not session:
        raise ValueError("Session for image not found")

    diagram_type = _infer_diagram_type(image.file_path)
    parent_ir_id = getattr(image, "ir_id", None)
    ir_version = _create_ir_version(
        db,
        session,
        diagram_type=diagram_type,
        svg_text=svg_text,
        reason=reason,
        parent_ir_id=parent_ir_id,
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


def ingest_input(
    db: DbSession,
    session: Session,
    files: Optional[List[str]],
    text: Optional[str],
    github_url: Optional[str] = None,
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
        save_json(f"{session.id}_architecture_plan.json", plan_data)

    plan_data = result.get("architecture_plan") or {}
    if plan_data:
        plan_model = ArchitecturePlanModel.model_validate(plan_data)

    if not settings.enable_ir:
        if plan_data:
            diagrams = generate_plantuml_from_plan(plan_model)
            files = render_diagrams(diagrams, f"{session.id}", output_format="svg")
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
                
                ir_version = _create_ir_version(
                    db,
                    session,
                    diagram_type=diagram_type,
                    svg_text=svg_text,
                    reason="architecture intent",
                    parent_ir_id=None,
                    ir_json={"intent": diagram_type},
                )
                
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

    planner = ConversationPlannerAgent()
    plan = get_latest_plan(db, session.id)
    images = list_images(db, session.id)
    diagrams = list_diagrams(db, session.id)
    ir_versions = list_ir_versions(db, session.id)
    history = [
        {"role": m.role, "content": m.content}
        for m in list_messages(db, session.id)[-10:]
    ]
    state = {
        "active_image_id": str(images[-1].id) if images else None,
        "diagram_types": [d.diagram_type for d in diagrams] or [ir.diagram_type for ir in ir_versions],
        "images": [
            {"id": str(img.id), "version": img.version, "reason": img.reason}
            for img in images
        ],
        "history": history,
        "github_url": session.source_repo,
        "input_text": session.input_text,
        "architecture_plan": plan.data if plan else None,
    }

    if not plan and not images and not ir_versions:
        if any(tok in (message or "").lower() for tok in ["diagram", "generate", "create", "story", "flow", "sequence"]):
            ingest_input(db, session, files=None, text=message)
            return {"intent": "generate", "response": "Generated.", "result": {}, "plan": {}, "tool_results": []}

    if not mcp_registry.get_tool("generate_architecture_plan"):
        register_mcp_tools(mcp_registry)

    def _is_visual_intent(text: str) -> bool:
        lowered = (text or "").lower()
        intent_tokens = [
            "calm", "minimal", "vibrant", "energetic", "highlight", "focus",
            "visual", "aesthetic", "contrast", "noise", "attention",
        ]
        return any(tok in lowered for tok in intent_tokens)

    def _select_image_by_hint(text: str) -> Image | None:
        lowered = (text or "").lower()
        if "semantic component" in lowered or "semantic_component" in lowered:
            for img in reversed(images):
                if "semantic_component" in (img.file_path or ""):
                    return img
        if "semantic container" in lowered or "semantic_container" in lowered:
            for img in reversed(images):
                if "semantic_container" in (img.file_path or ""):
                    return img
        if "semantic system" in lowered or "semantic_system_context" in lowered:
            for img in reversed(images):
                if "semantic_system_context" in (img.file_path or ""):
                    return img
        return images[-1] if images else None

    if _is_visual_intent(message) and ir_versions:
        target_img = _select_image_by_hint(message)
        target_ir = db.get(DiagramIR, target_img.ir_id) if target_img and target_img.ir_id else ir_versions[-1]
        if target_ir:
            svg_text = target_ir.svg_text
            if not svg_text and target_img and target_img.file_path and target_img.file_path.endswith(".svg"):
                try:
                    svg_text = read_text_file(str(Path(target_img.file_path)))
                except Exception:
                    svg_text = ""
            if not svg_text:
                svg_text = target_ir.svg_text or ""
            intent_ir, had_color = generate_semantic_intent(svg_text, message)
            ir_payload = {}
            if isinstance(target_ir.ir_json, dict):
                ir_payload.update(target_ir.ir_json)
            ir_payload["aesthetic_intent"] = intent_ir.to_dict()
            ir_version = _create_ir_version(
                db,
                session,
                diagram_type=target_ir.diagram_type,
                svg_text=svg_text,
                reason="semantic_intent",
                parent_ir_id=target_ir.id,
                ir_json=ir_payload,
                plantuml_text=target_ir.plantuml_text,
            )
            svg_file = render_ir_svg(svg_text, f"{session.id}_{target_ir.diagram_type}_{ir_version.version}")
            created_image = _create_image(
                db,
                session,
                file_path=svg_file,
                prompt=None,
                reason="semantic intent",
                ir_id=ir_version.id,
            )
            note = "Applied semantic visual intent." + (" (Direct color instructions were ignored.)" if had_color else "")
            db.add(
                Message(
                    session_id=session.id,
                    role="assistant",
                    content=note,
                    intent="semantic_intent",
                    image_id=created_image.id,
                    message_type="image",
                    image_version=created_image.version,
                    diagram_type=target_ir.diagram_type,
                    ir_id=ir_version.id,
                )
            )
            db.commit()
            return {
                "intent": "semantic_intent",
                "response": note,
                "result": {"diagram_type": target_ir.diagram_type},
                "plan": {},
                "tool_results": [],
            }

    # Aggressive fallback: detect sequence/plantuml/flow requests BEFORE calling planner
    lowered_msg = (message or "").lower()
    if plan and any(keyword in lowered_msg for keyword in ["sequence", "plantuml", "plant uml", "flow", "interaction"]):
        # Direct sequence generation - bypass planner
        intent = "generate_sequence"
        plan_result = {
            "intent": "generate_sequence",
            "plan": [{"tool": "generate_plantuml_sequence", "arguments": {}}],
            "diagram_count": None,
            "diagrams": [{"type": "sequence", "reason": "user requested"}],
        }
    else:
        plan_result = planner.plan(message, state, mcp_registry.list_tools())
        intent = plan_result.get("intent", "clarify")

    def _looks_like_color_request(text: str) -> bool:
        lowered = (text or "").lower()
        return any(token in lowered for token in [
            "color", "colour", "palette", "theme", "style", "aesthetic", "vibrant", "contrast",
            "highlight", "emphasis",
        ])

    def _select_image_by_hint(text: str) -> Image | None:
        lowered = (text or "").lower()
        if "semantic component" in lowered or "semantic_component" in lowered:
            for img in reversed(images):
                if "semantic_component" in (img.file_path or ""):
                    return img
        if "semantic container" in lowered or "semantic_container" in lowered:
            for img in reversed(images):
                if "semantic_container" in (img.file_path or ""):
                    return img
        if "semantic system" in lowered or "semantic_system_context" in lowered:
            for img in reversed(images):
                if "semantic_system_context" in (img.file_path or ""):
                    return img
        return images[-1] if images else None

    if _looks_like_color_request(message):
        target_img = _select_image_by_hint(message)
        if target_img and getattr(target_img, "ir_id", None):
            plan_result["intent"] = "edit_image"
            plan_result["target_image_id"] = str(target_img.id)
            plan_result["target_diagram_type"] = _infer_diagram_type(target_img.file_path)
            plan_result["instructions"] = message
            plan_result["requires_regeneration"] = False
            plan_result["plan"] = [
                {
                    "tool": "edit_diagram_ir",
                    "arguments": {"instruction": message, "ir_id": str(target_img.ir_id)},
                }
            ]
            intent = "edit_image"
    result: dict = {}

    diagram_count = plan_result.get("diagram_count")
    planned_diagrams = plan_result.get("diagrams") or []
    planned_types = [d.get("type") for d in planned_diagrams if isinstance(d, dict) and d.get("type")]

    tool_results: list[dict] = []
    created_image: Image | None = None
    assistant_messages: list[Message] = []
    for step in plan_result.get("plan", []) or []:
        tool_name = step.get("tool")
        args = dict(step.get("arguments", {}) or {})
        if not tool_name:
            continue

        if tool_name in {"generate_plantuml", "generate_diagram", "generate_multiple_diagrams", "edit_diagram_via_semantic_understanding", "edit_diagram_ir"}:
            if "output_name" not in args:
                args["output_name"] = f"{session.id}_{_next_version(db, session.id)}"

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
                    args["diagram_types"] = list(types)[:diagram_count]

        if tool_name in {"generate_plantuml", "render_image_from_plan", "explain_architecture", "generate_sequence_from_architecture", "generate_plantuml_sequence"}:
            if not args.get("architecture_plan"):
                latest_plan = get_latest_plan(db, session.id)
                if latest_plan:
                    args["architecture_plan"] = latest_plan.data
                else:
                    response_text = "I need an architecture plan to do that. Please generate from input first."
                    break

        if tool_name == "generate_sequence_from_architecture":
            if "github_url" not in args and session.source_repo:
                args["github_url"] = session.source_repo
            if "user_message" not in args:
                args["user_message"] = message
            if "output_name" not in args:
                args["output_name"] = f"{session.id}_sequence_{_next_version(db, session.id)}"
        
        if tool_name == "generate_plantuml_sequence":
            if "output_name" not in args:
                args["output_name"] = f"{session.id}_sequence_{_next_version(db, session.id)}"

        if tool_name == "generate_architecture_plan" and "content" not in args:
            if session.input_text:
                args["content"] = session.input_text
            else:
                response_text = "I need the original input to generate the architecture plan."
                break

        if tool_name == "edit_existing_image" and "image_id" not in args:
            if images:
                args["image_id"] = str(images[-1].id)
            else:
                response_text = "I need an image to edit. Generate a diagram first."
                break

        if tool_name in {"render_image_from_plan", "edit_existing_image", "edit_diagram_ir"} and "session_id" not in args:
            args["session_id"] = str(session.id)

        try:
            tool_output = mcp_registry.execute(
                tool_name,
                args,
                context={"db": db, "session": session, "session_id": str(session.id)},
            )
        except Exception as exc:
            response_text = f"Tool '{tool_name}' failed: {exc}"
            break
        tool_results.append({"tool": tool_name, "output": tool_output})

        if tool_name == "generate_architecture_plan":
            plan_data = tool_output.get("architecture_plan")
            if plan_data:
                db.add(ArchitecturePlanRecord(session_id=session.id, data=plan_data))
        elif tool_name in {"generate_plantuml", "generate_diagram", "generate_multiple_diagrams", "edit_diagram_via_semantic_understanding", "edit_diagram_ir", "generate_sequence_from_architecture", "generate_plantuml_sequence"}:
            for entry in tool_output.get("ir_entries", []) or []:
                diagram_type = entry.get("diagram_type") or "diagram"
                svg_text = entry.get("svg")
                svg_file = entry.get("svg_file")
                parent_ir_id = entry.get("parent_ir_id")
                if not svg_text:
                    continue
                ir_version = _create_ir_version(
                    db,
                    session,
                    diagram_type=diagram_type,
                    svg_text=svg_text,
                    reason=entry.get("reason") or intent,
                    parent_ir_id=_parse_uuid(parent_ir_id) if parent_ir_id else None,
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
        elif tool_name == "explain_architecture":
            result["explanation"] = tool_output.get("answer")

    if tool_results:
        if assistant_messages:
            # Created image messages, provide informative text
            diagram_types = set(msg.diagram_type for msg in assistant_messages if msg.diagram_type)
            if diagram_types:
                response_text = f"Generated {', '.join(sorted(diagram_types))} diagram(s)."
            else:
                response_text = ""
        else:
            response_text = result.get("explanation") or "Done."
    elif intent == "edit_image":
        latest_ir = list_ir_versions(db, session.id)[-1] if list_ir_versions(db, session.id) else None
        if latest_ir:
            edited_svg = edit_ir_svg(latest_ir.svg_text, plan_result.get("instructions") or message)
            ir_version = _create_ir_version(
                db,
                session,
                diagram_type=latest_ir.diagram_type,
                svg_text=edited_svg,
                reason="edit",
                parent_ir_id=latest_ir.id,
            )
            svg_file = render_ir_svg(edited_svg, f"{session.id}_{latest_ir.diagram_type}_{ir_version.version}")
            created_image = _create_image(
                db,
                session,
                file_path=svg_file,
                prompt=None,
                reason="edit",
                ir_id=ir_version.id,
            )
            response_text = "" if assistant_messages else "Applied edit to the diagram."
            assistant_messages.append(
                Message(
                    session_id=session.id,
                    role="assistant",
                    content="",
                    intent=intent,
                    image_id=created_image.id,
                    message_type="image",
                    image_version=created_image.version,
                    diagram_type=latest_ir.diagram_type,
                    ir_id=ir_version.id,
                )
            )
        else:
            response_text = "I need a diagram to edit. Generate one first."
    elif intent == "diagram_change":
        target_type = plan_result.get("target_diagram_type")
        ir_versions = list_ir_versions(db, session.id)
        latest_by_type: dict[str, DiagramIR] = {}
        for ir in ir_versions:
            latest_by_type[ir.diagram_type] = ir
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
            response_text = ""
            result = {"diagram_type": target_type}
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
        elif plan_result.get("requires_regeneration"):
            if session.input_text:
                ingest_input(db, session, files=None, text=session.input_text)
                response_text = "Regenerated architecture to include requested diagram."
                result = {"diagram_type": target_type}
            else:
                response_text = "I need the original input (file or text) to regenerate. Please re-upload or paste it."
                result = {}
        else:
            response_text = "Requested diagram type not available."
            result = {}
    elif intent == "regenerate":
        if session.input_text:
            result = ingest_input(db, session, files=None, text=session.input_text)
            response_text = "Regenerated architecture from input."
        else:
            response_text = "I need the original input (file or text) to regenerate. Please re-upload or paste it."
            result = {}
    elif intent == "explain":
        response_text = explain_architecture(plan.data if plan else {}, message)
        result = {}
    elif intent == "generate_sequence":
        # Should have been handled by tool execution loop
        if not tool_results:
            response_text = "Failed to generate sequence diagram. Please check if architecture plan exists."
        else:
            response_text = ""
        result = {}
    else:
        response_text = "Can you clarify what change or explanation you want?"
        result = {}

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
        "result": result,
        "plan": plan_result,
        "tool_results": tool_results,
    }


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
) -> DiagramIR:
    last = db.execute(
        select(DiagramIR).where(DiagramIR.session_id == session.id).order_by(DiagramIR.version.desc())
    ).scalars().first()
    if svg_text is None:
        logging.getLogger(__name__).warning("Creating IR version with empty svg_text for session %s diagram %s", session.id, diagram_type)
        svg_text = ""

    ir_version = DiagramIR(
        session_id=session.id,
        diagram_type=diagram_type,
        version=(last.version + 1) if last else 1,
        parent_ir_id=parent_ir_id,
        reason=reason,
        svg_text=svg_text,
        ir_json=ir_json,
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
