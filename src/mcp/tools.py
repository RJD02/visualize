"""MCP tool implementations and registration."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from openai import OpenAI

from src.agents.architect_agent import generate_architecture_plan_from_text
from src.agents.visual_agent import build_visual_prompt
from src.db_models import Image
from src.models.architecture_plan import ArchitecturePlan
from src.services.intent import explain_architecture
from src.tools.github_ingest import ingest_github_repo
from src.tools.image_versioning import add_version
from src.tools.plantuml_renderer import generate_plantuml_from_plan, render_diagrams, render_diagram_by_type
from src.tools.svg_ir import generate_svg_from_plan, edit_ir_svg
from src.db_models import DiagramIR
from src.tools.sdxl_renderer import run_sdxl, run_sdxl_edit
from src.tools.text_extractor import extract_text
from src.mcp.registry import MCPRegistry, MCPTool
from src.utils.config import settings
from src.renderers.renderer_ir import RendererIR
from src.renderers.router import render_ir
from src.renderers.translator import ir_to_mermaid, ir_to_structurizr_dsl, ir_to_plantuml
from src.renderers.mermaid_renderer import render_mermaid_svg
from src.renderers.structurizr_renderer import render_structurizr_svg
from src.renderers.plantuml_renderer import render_plantuml_svg_text
from src.renderers.renderer_ir import IRNode, IREdge, IRGroup


def _parse_uuid(value: str | UUID) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def tool_extract_text(context: Dict[str, Any], files: Optional[List[str]] = None, text: Optional[str] = None) -> Dict[str, Any]:
    content = extract_text(files=files, text=text)
    return {"content": content}


def tool_generate_architecture_plan(context: Dict[str, Any], content: str) -> Dict[str, Any]:
    plan = generate_architecture_plan_from_text(content)
    return {"architecture_plan": plan}


def tool_generate_plantuml(context: Dict[str, Any], architecture_plan: Dict[str, Any], output_name: str) -> Dict[str, Any]:
    if not architecture_plan:
        raise ValueError("architecture_plan is required")
    plan = ArchitecturePlan.parse_obj(architecture_plan)
    diagrams = generate_plantuml_from_plan(plan)
    files = render_diagrams(diagrams, output_name)
    return {"files": files}


def tool_generate_diagram(
    context: Dict[str, Any], architecture_plan: Dict[str, Any], output_name: str, diagram_type: str
) -> Dict[str, Any]:
    if not architecture_plan:
        raise ValueError("architecture_plan is required")
    plan = ArchitecturePlan.parse_obj(architecture_plan)
    result = generate_svg_from_plan(plan, diagram_type, f"{output_name}_{diagram_type}_1")
    return {"ir_entries": [{"diagram_type": diagram_type, "svg": result["svg"], "svg_file": result["svg_file"]}]}


def tool_generate_multiple_diagrams(
    context: Dict[str, Any], architecture_plan: Dict[str, Any], output_name: str, diagram_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    if not architecture_plan:
        raise ValueError("architecture_plan is required")
    plan = ArchitecturePlan.parse_obj(architecture_plan)
    types = diagram_types or list(plan.diagram_views)
    entries = []
    for idx, diag_type in enumerate(types):
        result = generate_svg_from_plan(plan, diag_type, f"{output_name}_{diag_type}_{idx + 1}")
        entries.append({"diagram_type": diag_type, "svg": result["svg"], "svg_file": result["svg_file"]})
    return {"ir_entries": entries}


def tool_render_image_from_plan(context: Dict[str, Any], architecture_plan: Dict[str, Any], output_name: str) -> Dict[str, Any]:
    plan = ArchitecturePlan.parse_obj(architecture_plan)
    prompt = build_visual_prompt(plan)
    image_file = run_sdxl(prompt, output_name)
    add_version(output_name, image_file)
    return {"image_file": image_file, "prompt": prompt}


def tool_edit_existing_image(
    context: Dict[str, Any], image_id: str, instruction: str, session_id: str
) -> Dict[str, Any]:
    prompt = instruction
    image_file = run_sdxl_edit(prompt, f"{session_id}_sdxl_edit")
    add_version(session_id, image_file)
    return {"image_file": image_file, "prompt": prompt, "image_id": image_id}


def tool_fetch_image_by_id(context: Dict[str, Any], image_id: str) -> Dict[str, Any]:
    db: DbSession = context["db"]
    image = db.get(Image, _parse_uuid(image_id))
    if not image:
        return {"image": None}
    return {
        "image": {
            "id": str(image.id),
            "version": image.version,
            "file_path": image.file_path,
            "prompt": image.prompt,
            "reason": image.reason,
        }
    }


def tool_list_image_versions(context: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    db: DbSession = context["db"]
    rows = db.query(Image).filter(Image.session_id == _parse_uuid(session_id)).order_by(Image.version).all()
    return {
        "images": [
            {
                "id": str(img.id),
                "version": img.version,
                "file_path": img.file_path,
                "prompt": img.prompt,
                "reason": img.reason,
            }
            for img in rows
        ]
    }


def tool_explain_architecture(context: Dict[str, Any], architecture_plan: Dict[str, Any], question: str) -> Dict[str, Any]:
    answer = explain_architecture(architecture_plan, question)
    return {"answer": answer}


def tool_ingest_github_repo(context: Dict[str, Any], repo_url: str) -> Dict[str, Any]:
    return ingest_github_repo(repo_url)


def _renderer_ir_from_plan(plan: ArchitecturePlan, diagram_type: str) -> RendererIR:
    nodes = []
    edges = []
    groups = []
    zone_map = {
        "clients": ("person", plan.zones.clients),
        "edge": ("service", plan.zones.edge),
        "core_services": ("component", plan.zones.core_services),
        "external_services": ("external", plan.zones.external_services),
        "data_stores": ("database", plan.zones.data_stores),
    }
    for zone, (kind, items) in zone_map.items():
        if not items:
            continue
        group_id = zone
        groups.append(IRGroup(id=group_id, label=zone.replace("_", " "), members=list(items)))
        for item in items:
            nodes.append(IRNode(id=item, kind=kind, label=item, group=group_id))
    for rel in plan.relationships:
        edges.append(IREdge(**{"from": rel.from_, "to": rel.to, "type": rel.type, "label": rel.description}))
    diagram_kind = "architecture"
    if diagram_type in {"sequence", "runtime"}:
        diagram_kind = "sequence"
    elif diagram_type in {"system_context", "container", "component"}:
        diagram_kind = "architecture"
    return RendererIR(
        diagram_kind=diagram_kind,
        layout=plan.visual_hints.layout,
        title=plan.system_name,
        nodes=nodes,
        edges=edges,
        groups=groups,
    )


def tool_build_renderer_ir(
    context: Dict[str, Any], architecture_plan: Dict[str, Any], diagram_type: str
) -> Dict[str, Any]:
    if not architecture_plan:
        raise ValueError("architecture_plan is required")
    plan = ArchitecturePlan.parse_obj(architecture_plan)
    ir = _renderer_ir_from_plan(plan, diagram_type)
    return {"ir": ir.to_dict()}


def tool_render_ir_router(
    context: Dict[str, Any], ir: Dict[str, Any], renderer_override: Optional[str] = None
) -> Dict[str, Any]:
    renderer_ir = RendererIR.parse_obj(ir)
    svg_text, choice = render_ir(renderer_ir, override=renderer_override)
    return {"svg": svg_text, "renderer": choice.renderer, "reason": choice.reason}


def tool_mermaid_renderer(context: Dict[str, Any], ir: Dict[str, Any]) -> Dict[str, Any]:
    renderer_ir = RendererIR.parse_obj(ir)
    svg_text = render_mermaid_svg(ir_to_mermaid(renderer_ir))
    return {"svg": svg_text}


def tool_structurizr_renderer(context: Dict[str, Any], ir: Dict[str, Any]) -> Dict[str, Any]:
    renderer_ir = RendererIR.parse_obj(ir)
    svg_text = render_structurizr_svg(ir_to_structurizr_dsl(renderer_ir))
    return {"svg": svg_text}


def tool_plantuml_renderer(context: Dict[str, Any], ir: Dict[str, Any]) -> Dict[str, Any]:
    renderer_ir = RendererIR.parse_obj(ir)
    svg_text = render_plantuml_svg_text(ir_to_plantuml(renderer_ir))
    return {"svg": svg_text}


def tool_edit_diagram_via_semantic_understanding(
    context: Dict[str, Any],
    architecture_plan: Dict[str, Any],
    instruction: str,
    output_name: str,
) -> Dict[str, Any]:
    if not architecture_plan:
        raise ValueError("architecture_plan is required")
    plan = ArchitecturePlan.parse_obj(architecture_plan)
    diagram_types = plan.diagram_views
    if not diagram_types:
        diagram_types = ["system_context"]

    if not settings.openai_api_key:
        target_type = diagram_types[0]
    else:
        client = OpenAI(api_key=settings.openai_api_key)
        prompt = (
            "Choose the best diagram type for this instruction. "
            f"Available: {diagram_types}. Instruction: {instruction}. "
            "Return only one type string."
        )
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "You select diagram types."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        target_type = (response.choices[0].message.content or "").strip()
        if target_type not in diagram_types:
            target_type = diagram_types[0]

    overrides = _infer_layout_overrides(instruction)
    result = generate_svg_from_plan(plan, target_type, f"{output_name}_{target_type}_1", overrides=overrides)
    return {"ir_entries": [{"diagram_type": target_type, "svg": result["svg"], "svg_file": result["svg_file"]}], "instruction": instruction}


def tool_edit_diagram_ir(
    context: Dict[str, Any],
    instruction: str,
    ir_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    db: DbSession = context["db"]
    ir: DiagramIR | None = None
    if ir_id:
        ir = db.get(DiagramIR, _parse_uuid(ir_id))
    elif session_id:
        rows = db.query(DiagramIR).filter(DiagramIR.session_id == _parse_uuid(session_id)).order_by(DiagramIR.version.desc()).all()
        ir = rows[0] if rows else None
    if not ir:
        raise ValueError("No IR version available to edit")
    svg_text = ir.svg_text or ""
    if not svg_text:
        image = db.query(Image).filter(Image.ir_id == ir.id).order_by(Image.version.desc()).first()
        if image and image.file_path and image.file_path.endswith(".svg"):
            try:
                svg_text = Path(image.file_path).read_text(encoding="utf-8")
            except Exception:
                svg_text = ""
    if not svg_text:
        raise ValueError("No SVG content available to edit")

    edited_svg = edit_ir_svg(svg_text, instruction)
    return {"ir_entries": [{"diagram_type": ir.diagram_type, "svg": edited_svg, "svg_file": None, "parent_ir_id": str(ir.id)}]}


def _infer_layout_overrides(instruction: str) -> Dict[str, Any]:
    if not instruction:
        return {}
    text = instruction.lower()
    overrides: Dict[str, Any] = {}
    if any(token in text for token in ["above", "below", "top", "bottom", "down", "up"]):
        overrides["layout"] = "top-down"
    if any(token in text for token in ["left", "right", "horizontal"]):
        overrides["layout"] = "left-to-right"

    zone_aliases = {
        "clients": ["clients", "client"],
        "edge": ["edge", "gateway", "api gateway"],
        "core_services": ["core services", "core_service", "core services block", "core_services"],
        "external_services": ["external services", "external", "third party", "external_services"],
        "data_stores": ["data stores", "datastore", "database", "data_stores"],
    }

    def _match_zone(fragment: str) -> Optional[str]:
        for zone, aliases in zone_aliases.items():
            if any(alias in fragment for alias in aliases):
                return zone
        return None

    move_above = re.search(r"move\s+(.+?)\s+above\s+(.+)", text)
    move_below = re.search(r"move\s+(.+?)\s+below\s+(.+)", text)
    zone_order: List[str] = []
    if move_above:
        first = _match_zone(move_above.group(1))
        second = _match_zone(move_above.group(2))
        if first and second:
            zone_order = [first, second]
    elif move_below:
        first = _match_zone(move_below.group(1))
        second = _match_zone(move_below.group(2))
        if first and second:
            zone_order = [second, first]
    else:
        for zone, aliases in zone_aliases.items():
            if any(alias in text for alias in aliases):
                if "above" in text or "top" in text:
                    zone_order.insert(0, zone)
                elif "below" in text or "down" in text or "bottom" in text:
                    zone_order.append(zone)

    if zone_order:
        overrides["zone_order"] = zone_order

    return overrides


def register_mcp_tools(registry: MCPRegistry) -> None:
    registry.register(
        MCPTool(
            name="extract_text",
            description="Extracts text from uploaded files or raw text input.",
            input_schema={"type": "object", "properties": {"files": {"type": "array", "items": {"type": "string"}}, "text": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"content": {"type": "string"}}},
            side_effects="none",
            handler=tool_extract_text,
        )
    )
    registry.register(
        MCPTool(
            name="generate_architecture_plan",
            description="Generates the architecture plan JSON from extracted text.",
            input_schema={"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]},
            output_schema={"type": "object", "properties": {"architecture_plan": {"type": "object"}}},
            side_effects="none",
            handler=tool_generate_architecture_plan,
        )
    )
    registry.register(
        MCPTool(
            name="generate_plantuml",
            description="Generates and renders PlantUML diagrams from an architecture plan.",
            input_schema={"type": "object", "properties": {"architecture_plan": {"type": "object"}, "output_name": {"type": "string"}}, "required": ["architecture_plan", "output_name"]},
            output_schema={"type": "object", "properties": {"files": {"type": "array", "items": {"type": "string"}}}},
            side_effects="writes diagram files",
            handler=tool_generate_plantuml,
        )
    )
    registry.register(
        MCPTool(
            name="generate_diagram",
            description="Generates a specific diagram type from an architecture plan.",
            input_schema={"type": "object", "properties": {"architecture_plan": {"type": "object"}, "output_name": {"type": "string"}, "diagram_type": {"type": "string"}}, "required": ["architecture_plan", "output_name", "diagram_type"]},
            output_schema={"type": "object", "properties": {"ir_entries": {"type": "array"}}},
            side_effects="writes diagram files",
            handler=tool_generate_diagram,
        )
    )
    registry.register(
        MCPTool(
            name="generate_multiple_diagrams",
            description="Generates multiple diagrams from an architecture plan.",
            input_schema={"type": "object", "properties": {"architecture_plan": {"type": "object"}, "output_name": {"type": "string"}, "diagram_types": {"type": "array", "items": {"type": "string"}}}, "required": ["architecture_plan", "output_name"]},
            output_schema={"type": "object", "properties": {"ir_entries": {"type": "array"}}},
            side_effects="writes diagram files",
            handler=tool_generate_multiple_diagrams,
        )
    )
    registry.register(
        MCPTool(
            name="build_renderer_ir",
            description="Build renderer-agnostic IR from an architecture plan.",
            input_schema={"type": "object", "properties": {"architecture_plan": {"type": "object"}, "diagram_type": {"type": "string"}}, "required": ["architecture_plan", "diagram_type"]},
            output_schema={"type": "object", "properties": {"ir": {"type": "object"}}},
            side_effects="none",
            handler=tool_build_renderer_ir,
        )
    )
    registry.register(
        MCPTool(
            name="render_ir_router",
            description="Render renderer-agnostic IR using the renderer router.",
            input_schema={"type": "object", "properties": {"ir": {"type": "object"}, "renderer_override": {"type": "string"}} , "required": ["ir"]},
            output_schema={"type": "object", "properties": {"svg": {"type": "string"}, "renderer": {"type": "string"}, "reason": {"type": "string"}}},
            side_effects="none",
            handler=tool_render_ir_router,
        )
    )
    registry.register(
        MCPTool(
            name="mermaid_renderer",
            description="Render renderer-agnostic IR using Mermaid (dockerized).",
            input_schema={"type": "object", "properties": {"ir": {"type": "object"}}, "required": ["ir"]},
            output_schema={"type": "object", "properties": {"svg": {"type": "string"}}},
            side_effects="none",
            handler=tool_mermaid_renderer,
        )
    )
    registry.register(
        MCPTool(
            name="structurizr_renderer",
            description="Render renderer-agnostic IR using Structurizr (dockerized).",
            input_schema={"type": "object", "properties": {"ir": {"type": "object"}}, "required": ["ir"]},
            output_schema={"type": "object", "properties": {"svg": {"type": "string"}}},
            side_effects="none",
            handler=tool_structurizr_renderer,
        )
    )
    registry.register(
        MCPTool(
            name="plantuml_renderer",
            description="Render renderer-agnostic IR using PlantUML (server).",
            input_schema={"type": "object", "properties": {"ir": {"type": "object"}}, "required": ["ir"]},
            output_schema={"type": "object", "properties": {"svg": {"type": "string"}}},
            side_effects="none",
            handler=tool_plantuml_renderer,
        )
    )
    registry.register(
        MCPTool(
            name="render_image_from_plan",
            description="Renders an SDXL image from an architecture plan.",
            input_schema={"type": "object", "properties": {"architecture_plan": {"type": "object"}, "output_name": {"type": "string"}}, "required": ["architecture_plan", "output_name"]},
            output_schema={"type": "object", "properties": {"image_file": {"type": "string"}, "prompt": {"type": "string"}}},
            side_effects="writes image files",
            handler=tool_render_image_from_plan,
        )
    )
    registry.register(
        MCPTool(
            name="edit_existing_image",
            description="Edits an existing image using a text instruction.",
            input_schema={"type": "object", "properties": {"image_id": {"type": "string"}, "instruction": {"type": "string"}, "session_id": {"type": "string"}}, "required": ["image_id", "instruction", "session_id"]},
            output_schema={"type": "object", "properties": {"image_file": {"type": "string"}, "prompt": {"type": "string"}, "image_id": {"type": "string"}}},
            side_effects="writes image files",
            handler=tool_edit_existing_image,
        )
    )
    registry.register(
        MCPTool(
            name="fetch_image_by_id",
            description="Fetch metadata for a specific image id.",
            input_schema={"type": "object", "properties": {"image_id": {"type": "string"}}, "required": ["image_id"]},
            output_schema={"type": "object", "properties": {"image": {"type": ["object", "null"]}}},
            side_effects="none",
            handler=tool_fetch_image_by_id,
        )
    )
    registry.register(
        MCPTool(
            name="list_image_versions",
            description="List image versions for a session.",
            input_schema={"type": "object", "properties": {"session_id": {"type": "string"}}, "required": ["session_id"]},
            output_schema={"type": "object", "properties": {"images": {"type": "array"}}},
            side_effects="none",
            handler=tool_list_image_versions,
        )
    )
    registry.register(
        MCPTool(
            name="explain_architecture",
            description="Explain an architecture plan based on a question.",
            input_schema={"type": "object", "properties": {"architecture_plan": {"type": "object"}, "question": {"type": "string"}}, "required": ["architecture_plan", "question"]},
            output_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
            side_effects="none",
            handler=tool_explain_architecture,
        )
    )
    registry.register(
        MCPTool(
            name="edit_diagram_via_semantic_understanding",
            description="Semantically edits a diagram based on instruction and architecture plan.",
            input_schema={"type": "object", "properties": {"architecture_plan": {"type": "object"}, "instruction": {"type": "string"}, "output_name": {"type": "string"}}, "required": ["architecture_plan", "instruction", "output_name"]},
            output_schema={"type": "object", "properties": {"ir_entries": {"type": "array"}, "diagram_type": {"type": "string"}}},
            side_effects="writes diagram files",
            handler=tool_edit_diagram_via_semantic_understanding,
        )
    )
    registry.register(
        MCPTool(
            name="edit_diagram_ir",
            description="Edits an SVG-as-IR diagram based on instruction.",
            input_schema={"type": "object", "properties": {"instruction": {"type": "string"}, "ir_id": {"type": "string"}, "session_id": {"type": "string"}}, "required": ["instruction"]},
            output_schema={"type": "object", "properties": {"ir_entries": {"type": "array"}}},
            side_effects="writes diagram files",
            handler=tool_edit_diagram_ir,
        )
    )
    registry.register(
        MCPTool(
            name="ingest_github_repo",
            description="Clone and analyze a GitHub repository URL into a normalized representation.",
            input_schema={"type": "object", "properties": {"repo_url": {"type": "string"}}, "required": ["repo_url"]},
            output_schema={"type": "object", "properties": {"repo_url": {"type": "string"}, "commit": {"type": "string"}, "summary": {"type": "object"}, "content": {"type": "string"}}},
            side_effects="clones repository to a temp directory",
            handler=tool_ingest_github_repo,
        )
    )
