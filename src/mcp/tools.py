"""MCP tool implementations and registration."""
from __future__ import annotations

import json
import typing
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session as DbSession

from src.agents.architect_agent import generate_architecture_plan_from_text
from src.agents.sequence_agent import SequenceGenerationAgent
from src.agents.visual_agent import build_visual_prompt
from src.db_models import DiagramIR, Image
from src.mcp.registry import MCPRegistry, MCPTool
from src.models.architecture_plan import ArchitecturePlan
from src.renderers.plantuml_renderer import render_plantuml_svg_text
from src.renderers.renderer_ir import RendererIR
from src.renderers.structurizr_renderer import render_structurizr_svg
from src.renderers.translator import ir_to_mermaid, ir_to_plantuml, ir_to_structurizr_dsl
from src.services.intent import explain_architecture
from src.services.styling_audit_service import record_styling_audit
from src.tools.github_ingest import ingest_github_repo
from src.tools.image_versioning import add_version
from src.tools.plantuml_renderer import generate_plantuml_from_plan, render_diagrams, render_llm_plantuml
from src.tools.plantuml_sequence import generate_plantuml_sequence_from_architecture
from src.tools.mermaid_renderer import render_llm_mermaid
from src.tools.sdxl_renderer import run_sdxl, run_sdxl_edit
from src.tools.svg_ir import build_ir_from_plan, generate_svg_from_plan, render_ir_svg, edit_ir_svg
from src.tools.text_extractor import extract_text
from src.utils.config import settings
from src.utils.file_utils import read_text_file
from src.utils.openai_client import get_openai_client


_COLOR_ALIASES = {
    "orange": "#FFA500",
    "yellow": "#F7D060",
    "red": "#E03131",
    "green": "#2F9E44",
    "blue": "#1C7ED6",
    "purple": "#7048E8",
    "teal": "#0CA678",
    "gray": "#868E96",
    "grey": "#868E96",
    "light": "#F8F9FA",
    "dark": "#212529",
    "white": "#FFFFFF",
    "black": "#000000",
}

_COLOR_PATTERN = re.compile(
    r"(#?[0-9a-fA-F]{3,8}|" + "|".join(sorted({c for c in _COLOR_ALIASES}, key=len, reverse=True)) + r")",
    re.IGNORECASE,
)

_THEME_PRESETS: Dict[str, Dict[str, str]] = {
    "pastel": {
        "background": "#FFF8F0",
        "primaryColor": "#FADAD8",
        "primaryBorderColor": "#F4B8C0",
        "primaryTextColor": "#3C3C3C",
        "lineColor": "#E5B9A8",
    },
    "dark": {
        "background": "#0F172A",
        "primaryColor": "#1E293B",
        "primaryTextColor": "#F8FAFC",
        "lineColor": "#475569",
    },
    "vibrant": {
        "background": "#0E7490",
        "primaryColor": "#F97316",
        "secondaryColor": "#14B8A6",
        "primaryTextColor": "#0F172A",
        "lineColor": "#0F766E",
    },
}


def _apply_theme_defaults(intent: Dict[str, Any]) -> Dict[str, Any]:
    theme_name = str(intent.get("theme") or "").lower()
    preset = _THEME_PRESETS.get(theme_name)
    if not preset:
        return intent
    block = intent.setdefault("blockColors", {})
    if preset.get("primaryColor") and "primary" not in block:
        block["primary"] = _resolve_color(preset["primaryColor"])
    if preset.get("secondaryColor") and "secondary" not in block:
        block["secondary"] = _resolve_color(preset["secondaryColor"])
    text_style = intent.setdefault("textStyle", {})
    if preset.get("primaryTextColor") and "fontColor" not in text_style:
        text_style["fontColor"] = _resolve_color(preset["primaryTextColor"])
    edge_style = intent.setdefault("edgeStyle", {})
    if preset.get("lineColor") and "strokeColor" not in edge_style:
        edge_style["strokeColor"] = _resolve_color(preset["lineColor"])
    return intent


def _resolve_color(value: str | dict | None) -> str:
    if value is None:
        return "#333333"
    if isinstance(value, dict):
        value = value.get("value") or value.get("color") or ""
    text = str(value).strip()
    if not text:
        return "#333333"
    if re.match(r"^#[0-9a-fA-F]{3,8}$", text):
        return text
    if re.match(r"^[0-9a-fA-F]{3,8}$", text):
        return f"#{text}"
    lowered = text.lower()
    if lowered in _COLOR_ALIASES:
        return _COLOR_ALIASES[lowered]
    return "#333333"


def _blank_intent() -> Dict[str, Any]:
    return {
        "theme": None,
        "blockColors": {},
        "textStyle": {},
        "edgeStyle": {},
    }


def extract_styling_intent(value: typing.Union[str, dict, None]) -> Dict[str, Any]:
    def _ensure_section(data: Any) -> Dict[str, Any]:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return {}

    if isinstance(value, dict):
        intent = _blank_intent()
        intent["theme"] = value.get("theme")
        intent["blockColors"] = _ensure_section(value.get("blockColors"))
        intent["textStyle"] = _ensure_section(value.get("textStyle"))
        intent["edgeStyle"] = _ensure_section(value.get("edgeStyle"))
        if "primary" in intent["blockColors"]:
            intent["blockColors"]["primary"] = _resolve_color(intent["blockColors"].get("primary"))
        if "secondary" in intent["blockColors"]:
            intent["blockColors"]["secondary"] = _resolve_color(intent["blockColors"].get("secondary"))
        if "fontColor" in intent["textStyle"]:
            intent["textStyle"]["fontColor"] = _resolve_color(intent["textStyle"].get("fontColor"))
        if "strokeColor" in intent["edgeStyle"]:
            intent["edgeStyle"]["strokeColor"] = _resolve_color(intent["edgeStyle"].get("strokeColor"))
        return _apply_theme_defaults(intent)

    text = (value or "").strip()
    if not text:
        return _blank_intent()

    lowered = text.lower()
    intent = _blank_intent()

    if "pastel" in lowered:
        intent["theme"] = "pastel"
    elif "dark" in lowered:
        intent["theme"] = "dark"
    elif "vibrant" in lowered:
        intent["theme"] = "vibrant"

    found_colors: list[str] = []
    for match in _COLOR_PATTERN.findall(text):
        normalized = _resolve_color(match)
        if normalized not in found_colors:
            found_colors.append(normalized)

    if found_colors:
        intent["blockColors"]["primary"] = found_colors[0]
    if len(found_colors) > 1:
        intent["blockColors"]["secondary"] = found_colors[1]

    if re.search(r"\bbold\b|\bstrong\b", lowered):
        intent["textStyle"]["fontWeight"] = "bold"
    if re.search(r"(light|white)\s+text", lowered):
        intent["textStyle"]["fontColor"] = "#F8F9FA"
    elif re.search(r"dark\s+text", lowered):
        intent["textStyle"]["fontColor"] = "#212529"

    if "edge" in lowered or "line" in lowered or "border" in lowered:
        width = "2px"
        if "thick" in lowered or "bold" in lowered:
            width = "3px"
        elif "thin" in lowered or "narrow" in lowered:
            width = "1px"
        intent["edgeStyle"]["strokeWidth"] = width
        if found_colors:
            intent["edgeStyle"]["strokeColor"] = found_colors[-1]

    return _apply_theme_defaults(intent)


def _build_mermaid_style_block(intent: dict) -> str:
    theme_name = (intent.get("theme") or "") if isinstance(intent, dict) else ""
    theme_vars: dict[str, Any] = dict(_THEME_PRESETS.get(str(theme_name).lower(), {}))
    class_defs: list[str] = []
    block_colors = intent.get("blockColors", {}) if isinstance(intent, dict) else {}
    text_style = intent.get("textStyle", {}) if isinstance(intent, dict) else {}
    edge_style = intent.get("edgeStyle", {}) if isinstance(intent, dict) else {}

    if block_colors.get("primary"):
        theme_vars["primaryColor"] = _resolve_color(block_colors["primary"])
        theme_vars.setdefault("primaryBorderColor", theme_vars["primaryColor"])
    if block_colors.get("secondary"):
        theme_vars["secondaryColor"] = _resolve_color(block_colors["secondary"])
    if text_style.get("fontColor"):
        theme_vars["primaryTextColor"] = _resolve_color(text_style["fontColor"])
    if edge_style.get("strokeColor"):
        theme_vars["lineColor"] = _resolve_color(edge_style["strokeColor"])

    if text_style.get("fontWeight") == "bold":
        class_defs.append("classDef emphasized font-weight:bold;")

    block = []
    if theme_vars:
        block.append(f"%%{{init: {{'theme': 'base', 'themeVariables': {json.dumps(theme_vars)}}}}}%%")
    if class_defs:
        block.extend(class_defs)
    return "\n".join(block) if block else "%%{init: {'theme': 'base'}}%%"


def _infer_diagram_type_from_path(path: str | None) -> str | None:
    if not path:
        return None
    name = Path(path).stem.lower()
    for candidate in ["system_context", "container", "component", "sequence", "runtime", "diagram"]:
        if candidate in name:
            return candidate
    return None


_ROLE_KIND_MAP = {
    "client": "person",
    "actor": "person",
    "gateway": "container",
    "service": "component",
    "external": "system",
    "db": "database",
    "data_store": "database",
}

_ROLE_BY_ZONE = {
    "clients": "actor",
    "edge": "gateway",
    "core_services": "service",
    "external_services": "external",
    "data_stores": "data_store",
}

_ACTOR_LABEL_HINTS = ("captain", "operator", "pilot", "user", "crew", "human")
_EXTERNAL_LABEL_HINTS = ("ship", "boat", "vessel")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", (value or "").strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "item"


_MERMAID_IR_PROMPT = """You are a diagram translation engine.

Task:
- Convert the provided renderer-agnostic IR into a Mermaid flowchart diagram.

Constraints:
- Output ONLY Mermaid syntax, no prose, no markdown fences.
- Use flowchart syntax (graph/flowchart) with the provided direction.
- Preserve all nodes and edges from the IR.
- Use concise labels, but do not remove semantic meaning.
- Use human/actor nodes when kind == person.
- Use database shapes for kind == database.
- Use double-circle for kind == system/external.
- Avoid Mermaid init blocks unless explicitly instructed.

Context:
- System name: {system_name}
- Diagram type: {diagram_type}
- Diagram kind: {diagram_kind}
- Layout: {layout}
- Narrative (if any): {narrative}
- Rendering hints: {rendering_hints}

Renderer IR (JSON):
{ir_json}
"""


def _llm_generate_mermaid_from_ir(
    renderer_ir: RendererIR,
    *,
    diagram_type: str,
    plan: ArchitecturePlan,
    context: Dict[str, Any] | None = None,
) -> str:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for LLM Mermaid generation")
    client = get_openai_client()
    ir_json = json.dumps(renderer_ir.to_dict(), indent=2)
    prompt = _MERMAID_IR_PROMPT.format(
        system_name=plan.system_name,
        diagram_type=diagram_type,
        diagram_kind=plan.diagram_kind or diagram_type,
        layout=plan.visual_hints.layout,
        narrative=plan.narrative or "",
        rendering_hints=json.dumps(plan.rendering_hints or {}, indent=2),
        ir_json=ir_json,
    )
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": "Return ONLY Mermaid flowchart syntax."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    raw = (response.choices[0].message.content or "").strip()
    return raw


def _infer_role_from_label(label: str) -> str | None:
    lowered = (label or "").lower()
    if any(tok in lowered for tok in _ACTOR_LABEL_HINTS):
        return "actor"
    if any(tok in lowered for tok in _EXTERNAL_LABEL_HINTS):
        return "external"
    return None


def _build_renderer_ir_from_plan(plan: ArchitecturePlan, diagram_type: str, overrides: Dict[str, Any] | None = None) -> RendererIR:
    overrides = overrides or {}
    base_ir = build_ir_from_plan(plan, diagram_type, overrides=overrides)
    description_map: dict[tuple[str, str], str] = {}
    for rel in plan.relationships:
        key = (rel.from_, rel.to)
        description_map[key] = rel.description

    zone_map = {
        "clients": list(plan.zones.clients),
        "edge": list(plan.zones.edge),
        "core_services": list(plan.zones.core_services),
        "external_services": list(plan.zones.external_services),
        "data_stores": list(plan.zones.data_stores),
    }
    all_labels: list[str] = []
    for items in zone_map.values():
        all_labels.extend(list(items))
    for rel in plan.relationships:
        all_labels.extend([rel.from_, rel.to])
    seen_labels: set[str] = set()
    nodes = []
    groups: dict[str, list[str]] = {}
    for label in all_labels:
        if not label or label in seen_labels:
            continue
        seen_labels.add(label)
        node_id = f"node_{_slug(label)}"
        zone = next((z for z, items in zone_map.items() if label in items), None)
        role = _ROLE_BY_ZONE.get(zone) if zone else _infer_role_from_label(label) or "service"
        kind = _ROLE_KIND_MAP.get(role, "component")
        nodes.append({"id": node_id, "label": label, "kind": kind, "group": zone or None})
        if zone:
            groups.setdefault(zone, []).append(node_id)
    label_to_id: dict[str, str] = {node["label"]: node["id"] for node in nodes}

    edges = []
    diagram_kind = (plan.diagram_kind or "").lower()
    if diagram_kind in {"story", "flow", "sequence"}:
        for rel in plan.relationships:
            from_id = label_to_id.get(rel.from_)
            to_id = label_to_id.get(rel.to)
            if not from_id or not to_id:
                continue
            edges.append({
                "from": from_id,
                "to": to_id,
                "type": rel.type,
                "label": rel.description or rel.type,
            })
    else:
        for edge in base_ir.edges:
            label = None
            for rel in plan.relationships:
                from_id = label_to_id.get(rel.from_)
                to_id = label_to_id.get(rel.to)
                if from_id == edge.from_id and to_id == edge.to_id:
                    label = rel.description or rel.type
                    break
            if not label:
                label = description_map.get((edge.from_id, edge.to_id))
            edges.append({"from": edge.from_id, "to": edge.to_id, "type": edge.rel_type, "label": label or edge.rel_type})

    group_list = []
    if plan.visual_hints.group_by_zone and (plan.diagram_kind or "").lower() not in {"story", "flow", "sequence"}:
        for zone, members in groups.items():
            if members:
                group_list.append({"id": zone, "label": zone, "members": members})

    return RendererIR(
        diagram_kind=plan.diagram_kind or diagram_type,
        layout=plan.visual_hints.layout,
        title=plan.system_name,
        nodes=nodes,
        edges=edges,
        groups=group_list,
    )


def _resolve_render_provider(plan: ArchitecturePlan | object, diagram_type: str, rendering_service: str | None) -> str:
    token = (rendering_service or "").lower().strip()
    if token in {"llm_mermaid", "mermaid"}:
        return "mermaid"
    if token in {"llm_plantuml", "plantuml"}:
        return "plantuml"
    if token == "structurizr":
        return "structurizr"
    hint = None
    plan_hints = getattr(plan, "rendering_hints", None)
    if isinstance(plan_hints, dict):
        hint = str(plan_hints.get("preferred_renderer") or "").lower().strip()
    if hint in {"plantuml", "mermaid", "structurizr"}:
        return hint
    diagram_kind = str(getattr(plan, "diagram_kind", "") or "").lower().strip()
    if diagram_kind in {"story", "flow", "sequence"}:
        return "mermaid"
    if diagram_type in {"sequence", "runtime", "flow", "story"}:
        return "mermaid"
    return "plantuml"


def _parse_uuid(value: str | UUID | None) -> UUID:
    if isinstance(value, UUID):
        return value
    if value is None:
        raise ValueError("UUID value required")
    try:
        return UUID(str(value))
    except ValueError:
        # Allow deterministic UUIDs for synthetic identifiers (e.g., diagram-test)
        return uuid.uuid5(uuid.NAMESPACE_URL, str(value))


def _build_plantuml_style_block(intent: dict) -> str:
    """Return PlantUML `skinparam` and `<style>` sections to apply styling.
    """
    lines: list[str] = []
    if intent.get("theme") == "pastel":
        lines.append("skinparam backgroundColor #FFF8F0")
        lines.append("skinparam componentBackgroundColor #FFD8A8")
    primary = intent.get("blockColors", {}).get("primary")
    if primary:
        lines.append(f"skinparam componentBackgroundColor {_resolve_color(primary)}")
    # Text style
    txt = intent.get("textStyle", {}).get("fontColor")
    if txt:
        lines.append(f"skinparam defaultTextColor {_resolve_color(txt)}")
    if intent.get("textStyle", {}).get("fontWeight") == "bold":
        lines.append("skinparam defaultFontStyle bold")

    # Add <style> block for finer selectors
    style_lines = ["<style>", "  <![CDATA["]
    if intent.get("edgeStyle", {}).get("strokeColor"):
        color = _resolve_color(intent["edgeStyle"]["strokeColor"])
        width = intent.get("edgeStyle", {}).get("strokeWidth", "2px")
        style_lines.append(f"    svg path.edge {{ stroke: {color}; stroke-width: {width}; }}")
    if intent.get("textStyle", {}).get("fontWeight"):
        style_lines.append(f"    svg text {{ font-weight: {intent['textStyle']['fontWeight']}; }}")
    style_lines.append("  ]]>\n</style>")
    if len(style_lines) > 2:
        lines.append("\n".join(style_lines))

    return "\n".join(lines)


def apply_post_svg_styles(svg_text: str, intent: dict, return_details: bool = False):
    """Parse SVG and inject scoped <style> block and inline attribute changes.

    - Injects `<style>` in the top-level `<svg>` element.
    - Applies inline `fill` to rects/nodes when blockColors provided.
    - Applies text styling to `<text>` elements.
    """
    try:
        parser = ET.XMLParser(encoding="utf-8")
        root = ET.fromstring(svg_text.encode("utf-8"), parser=parser)
    except Exception:
        # Fallback: if parsing fails, return original
        return svg_text

    nsmap = {k: v for k, v in root.attrib.items() if k.startswith("xmlns")}

    style_rules: list[str] = []
    # Block colors -> apply to rects and elements with class 'node' or 'component'
    primary = intent.get("blockColors", {}).get("primary")
    secondary = intent.get("blockColors", {}).get("secondary")
    if primary:
        style_rules.append(f".node, .component, rect {{ fill: {_resolve_color(primary)} !important; }}")
    if secondary:
        style_rules.append(f".node.secondary, .component.secondary {{ fill: {_resolve_color(secondary)} !important; }}")

    # Text styles
    txt = intent.get("textStyle", {})
    if txt.get("fontWeight"):
        style_rules.append(f"text {{ font-weight: {txt['fontWeight']} !important; }}")
    if txt.get("fontColor"):
        style_rules.append(f"text {{ fill: {_resolve_color(txt['fontColor'])} !important; }}")

    # Edge styles
    edge = intent.get("edgeStyle", {})
    if edge.get("strokeColor"):
        style_rules.append(f"path, line {{ stroke: {_resolve_color(edge['strokeColor'])} !important; }}")
    if edge.get("strokeWidth"):
        style_rules.append(f"path, line {{ stroke-width: {edge['strokeWidth']} !important; }}")

    if style_rules:
        style_el = ET.Element("style")
        style_el.text = "\n".join(style_rules)
        # Insert style as first child
        root.insert(0, style_el)

    # Inline modifications for text nodes to ensure compatibility
    if txt.get("fontWeight") or txt.get("fontColor"):
        for t in root.findall('.//{http://www.w3.org/2000/svg}text'):
            if txt.get("fontWeight"):
                t.set("font-weight", txt["fontWeight"])
            if txt.get("fontColor"):
                t.set("fill", _resolve_color(txt["fontColor"]))

    # Serialize back
    try:
        animated_svg = ET.tostring(root, encoding="unicode")
    except Exception:
        animated_svg = svg_text

    if not return_details:
        return animated_svg

    details = {
        "style_rules": style_rules,
        "applied_primary": bool(primary),
        "applied_secondary": bool(secondary),
        "text_rules": bool(txt.get("fontWeight") or txt.get("fontColor")),
        "edge_rules": bool(edge.get("strokeColor") or edge.get("strokeWidth")),
    }
    return animated_svg, details


def tool_svg_styling_agent(
    context: Dict[str, typing.Any],
    svg_text: typing.Optional[str] = None,
    renderer: typing.Optional[str] = None,
    renderer_input: typing.Optional[dict] = None,
    styling_intent: typing.Union[str, dict] = None,
    target_engine: typing.Optional[str] = None,
    diagram_id: typing.Optional[str] = None,
    diagram_type: typing.Optional[str] = None,
    mode: typing.Optional[str] = None,
    ir_id: typing.Optional[str] = None,
    user_prompt: typing.Optional[str] = None,
    planId: typing.Optional[str] = None,
    renderingService: typing.Optional[str] = None,
    llmDiagram: typing.Optional[typing.Union[str, dict]] = None,
) -> Dict[str, typing.Any]:
    """Apply styling intent either before rendering (pre-SVG) or after SVG exists."""

    intent = extract_styling_intent(styling_intent or {})
    db: DbSession | None = context.get("db")
    session_obj = context.get("session")
    session_id_value = context.get("session_id") or getattr(session_obj, "id", None)
    session_uuid = _parse_uuid(session_id_value) if session_id_value else None
    diagram_uuid = _parse_uuid(diagram_id) if diagram_id else None
    plan_identifier = planId or context.get("plan_id")
    llm_payload = _normalize_llm_diagram_payload(llmDiagram)
    resolved_mode = (mode or ("pre-svg" if renderer_input else "post-svg")).lower()
    execution_steps: list[str] = ["Extracted styling intent from prompt or payload."]
    reasoning_parts: list[str] = [
        "Detected directives: " + ", ".join(k for k, v in intent.items() if v)
    ]
    user_prompt_value = user_prompt or context.get("user_message") or context.get("styling_prompt") or context.get("prompt")

    svg_before = svg_text
    renderer_input_before = None
    renderer_input_after = None
    resolved_diagram_type = diagram_type

    if db and diagram_uuid:
        image_record = db.get(Image, diagram_uuid)
        if image_record and not resolved_diagram_type:
            resolved_diagram_type = _infer_diagram_type_from_path(image_record.file_path)
        if svg_text is None and image_record:
            target_ir_id = ir_id or getattr(image_record, "ir_id", None)
            svg_candidate = None
            if target_ir_id:
                ir_record = db.get(DiagramIR, _parse_uuid(target_ir_id))
                if ir_record:
                    svg_candidate = ir_record.svg_text
            if not svg_candidate and image_record.file_path:
                try:
                    svg_candidate = read_text_file(image_record.file_path)
                except Exception:
                    svg_candidate = None
            if svg_candidate:
                svg_text = svg_candidate
        svg_before = svg_text

    source_value = None
    if renderer_input:
        source_value = renderer_input.get("source") if isinstance(renderer_input, dict) else renderer_input
    if source_value:
        renderer_input_before = str(source_value)

    styling_plan = {
        "mode": "pre-svg" if resolved_mode.startswith("pre") else "post-svg",
        "renderer": (target_engine or renderer or "mermaid") if renderer_input else None,
        "intent": intent,
    }
    if renderingService:
        styling_plan["rendering_service"] = renderingService
    if llm_payload:
        styling_plan["llm_schema_version"] = llm_payload["schema_version"]

    audit_id: str | None = None

    if renderer_input_before:
        engine = (target_engine or renderer or "mermaid").lower()
        if engine == "mermaid":
            style_block = _build_mermaid_style_block(intent)
            renderer_input_after = f"{style_block}\n\n{renderer_input_before}" if renderer_input_before else style_block
            execution_steps.append("Prefixed mermaid source with themeVariables/classDefs.")
            reasoning_parts.append("Selected mermaid pre-SVG styling to preserve renderer determinism.")
            styling_plan["mode"] = "pre-svg"
            result_payload = {
                "success": True,
                "renderer": "mermaid",
                "renderer_text": renderer_input_after,
                "intent": intent,
                "mode": "pre-svg",
                "diagram_id": str(diagram_uuid) if diagram_uuid else diagram_id,
                "diagram_type": resolved_diagram_type,
            }
        elif engine in ("plantuml", "plant-uml"):
            style_block = _build_plantuml_style_block(intent)
            renderer_input_after = f"{style_block}\n\n{renderer_input_before}" if renderer_input_before else style_block
            execution_steps.append("Injected PlantUML skinparam/style directives pre-render.")
            reasoning_parts.append("Used PlantUML skinparam because renderer target is plantuml.")
            styling_plan["mode"] = "pre-svg"
            styling_plan["renderer"] = "plantuml"
            result_payload = {
                "success": True,
                "renderer": "plantuml",
                "renderer_text": renderer_input_after,
                "intent": intent,
                "mode": "pre-svg",
                "diagram_id": str(diagram_uuid) if diagram_uuid else diagram_id,
                "diagram_type": resolved_diagram_type,
            }
        else:
            return {"success": False, "error": "Unknown renderer or insufficient inputs", "intent": intent}
    else:
        resolved_mode = "post-svg"
        if not svg_text:
            return {"success": False, "error": "svg_text required for post-SVG styling", "intent": intent}
        updated_svg = apply_post_svg_styles(svg_text, intent)
        execution_steps.append("Applied post-SVG transformations to nodes, edges, and text elements.")
        reasoning_parts.append("Chose post-SVG mode because renderer source was unavailable.")
        svg_before = svg_text
        styling_plan["mode"] = "post-svg"
        styling_plan["renderer"] = None
        result_payload = {
            "success": True,
            "mode": "post-svg",
            "svg": updated_svg,
            "applied_intent": intent,
            "diagram_id": str(diagram_uuid) if diagram_uuid else diagram_id,
            "diagram_type": resolved_diagram_type,
        }
        svg_text = updated_svg

    if db and session_uuid:
        audit = record_styling_audit(
            db,
            session_id=session_uuid,
            plan_id=plan_identifier,
            diagram_id=diagram_uuid,
            diagram_type=resolved_diagram_type,
            user_prompt=user_prompt_value,
            llm_format=(llm_payload or {}).get("format"),
            llm_diagram=(llm_payload or {}).get("diagram"),
            extracted_intent=intent,
            styling_plan=styling_plan,
            execution_steps=execution_steps,
            agent_reasoning=" ".join(reasoning_parts),
            mode=styling_plan["mode"],
            renderer_input_before=renderer_input_before,
            renderer_input_after=renderer_input_after,
            svg_before=svg_before,
            svg_after=svg_text if styling_plan["mode"] == "post-svg" else None,
        )
        audit_id = str(audit.id)
        result_payload["audit_id"] = audit_id

    result_payload.setdefault("file_path", None)
    result_payload.setdefault("warnings", [])
    if renderingService and "rendering_service" not in result_payload:
        result_payload["rendering_service"] = renderingService
    return result_payload


def _normalize_renderer_input(renderer_input: typing.Any) -> dict | None:
    if renderer_input is None:
        return None
    if isinstance(renderer_input, dict):
        return renderer_input
    text_value = str(renderer_input).strip()
    if not text_value:
        return None
    return {"source": text_value}


def _normalize_llm_diagram_payload(value: typing.Any) -> dict | None:
    if not value:
        return None
    payload = value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    diagram_text = str(payload.get("diagram") or payload.get("text") or "").strip()
    if not diagram_text:
        return None
    fmt = str(payload.get("format") or payload.get("type") or "plantuml").lower()
    if fmt.startswith("plant"):
        fmt = "plantuml"
    elif fmt.startswith("mermaid"):
        fmt = "mermaid"
    else:
        return None
    schema_version = payload.get("schema_version") or payload.get("version") or 1
    try:
        schema_version = int(schema_version)
    except (TypeError, ValueError):
        schema_version = 1
    return {"format": fmt, "diagram": diagram_text, "schema_version": schema_version}


def _ensure_context_payload(
    context: Dict[str, typing.Any] | None,
    *,
    session_id: str | None,
    user_prompt: str | None,
    plan_id: str | None = None,
) -> Dict[str, typing.Any]:
    payload = dict(context or {})
    if session_id and not payload.get("session_id"):
        payload["session_id"] = session_id
    if user_prompt and not payload.get("user_message"):
        payload["user_message"] = user_prompt
    if plan_id and not payload.get("plan_id"):
        payload["plan_id"] = plan_id
    return payload


def _build_render_audit_context(context: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not context:
        return None
    session_obj = context.get("session")
    session_id = context.get("session_id")
    if not session_id and session_obj is not None:
        session_id = getattr(session_obj, "id", None)
    return {
        "db": context.get("db"),
        "session_id": session_id,
        "plan_id": context.get("plan_id"),
        "user_prompt": context.get("user_message"),
    }


def _format_styling_result(result: Dict[str, Any], mode: str) -> Dict[str, Any]:
    formatted = dict(result or {})
    audit_id = formatted.get("audit_id")
    if audit_id and "auditId" not in formatted:
        formatted["auditId"] = audit_id
    if mode == "pre-svg" and formatted.get("renderer_text") and "rendererInputAfter" not in formatted:
        formatted["rendererInputAfter"] = formatted["renderer_text"]
    if mode == "post-svg" and formatted.get("svg") and "svgAfter" not in formatted:
        formatted["svgAfter"] = formatted["svg"]
    formatted.setdefault("mode", mode)
    return formatted


def tool_apply_pre_svg_styling(
    context: Dict[str, typing.Any] | None,
    diagramId: str | None = None,
    sessionId: str | None = None,
    userPrompt: str | None = None,
    rendererInput: typing.Any = None,
    renderer: str | None = None,
    diagramType: str | None = None,
    stylingIntent: typing.Union[str, dict, None] = None,
    targetEngine: str | None = None,
    irId: str | None = None,
    mode: str | None = None,
    planId: str | None = None,
    renderingService: str | None = None,
    llmDiagram: typing.Union[str, dict, None] = None,
) -> Dict[str, Any]:
    normalized_input = _normalize_renderer_input(rendererInput)
    if not normalized_input or not normalized_input.get("source"):
        raise ValueError("rendererInput with a 'source' value is required for pre-SVG styling")
    prompt_value = userPrompt if userPrompt else (stylingIntent if isinstance(stylingIntent, str) else None)
    enriched_context = _ensure_context_payload(context, session_id=sessionId, user_prompt=prompt_value, plan_id=planId)
    resolved_mode = mode or "pre-svg"
    base_result = tool_svg_styling_agent(
        context=enriched_context,
        renderer=renderer or normalized_input.get("renderer"),
        renderer_input=normalized_input,
        styling_intent=stylingIntent or userPrompt,
        target_engine=targetEngine or normalized_input.get("target_engine"),
        diagram_id=diagramId,
        diagram_type=diagramType or normalized_input.get("diagram_type"),
        mode=resolved_mode,
        ir_id=irId,
        planId=planId,
        renderingService=renderingService,
        llmDiagram=llmDiagram,
    )
    return _format_styling_result(base_result, mode=resolved_mode)


def tool_apply_post_svg_styling(
    context: Dict[str, typing.Any] | None,
    diagramId: str | None = None,
    sessionId: str | None = None,
    userPrompt: str | None = None,
    svgText: str | None = None,
    diagramType: str | None = None,
    stylingIntent: typing.Union[str, dict, None] = None,
    irId: str | None = None,
    mode: str | None = None,
    planId: str | None = None,
    renderingService: str | None = None,
    llmDiagram: typing.Union[str, dict, None] = None,
) -> Dict[str, Any]:
    if (svgText is None or not str(svgText).strip()) and not diagramId:
        raise ValueError("svgText is required for post-SVG styling when no diagramId is provided")
    prompt_value = userPrompt if userPrompt else (stylingIntent if isinstance(stylingIntent, str) else None)
    enriched_context = _ensure_context_payload(context, session_id=sessionId, user_prompt=prompt_value, plan_id=planId)
    base_result = tool_svg_styling_agent(
        context=enriched_context,
        svg_text=svgText,
        styling_intent=stylingIntent or userPrompt,
        diagram_id=diagramId,
        diagram_type=diagramType,
        mode=mode or "post-svg",
        ir_id=irId,
        planId=planId,
        renderingService=renderingService,
        llmDiagram=llmDiagram,
    )
    return _format_styling_result(base_result, mode=mode or "post-svg")


# Register the SVG styling MCP tool
SVG_STYLING_TOOL = MCPTool(
    name="svg_styling_agent",
    description="Apply styling intent to diagrams (pre-SVG renderer syntax or post-SVG transformations)",
    input_schema={
        "type": "object",
        "properties": {
            "svg_text": {"type": ["string", "null"]},
            "renderer": {"type": "string"},
            "renderer_input": {"type": "object"},
            "styling_intent": {"type": ["string", "object"]},
            "target_engine": {"type": "string"},
            "diagram_id": {"type": ["string", "null"]},
            "diagram_type": {"type": ["string", "null"]},
            "mode": {"type": ["string", "null"]},
            "ir_id": {"type": ["string", "null"]},
            "planId": {"type": ["string", "null"]},
            "renderingService": {"type": ["string", "null"]},
            "llmDiagram": {"type": ["object", "string", "null"]},
        }
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "svg": {"type": ["string", "null"]},
            "renderer": {"type": ["string", "null"]},
            "renderer_text": {"type": ["string", "null"]},
            "mode": {"type": ["string", "null"]},
            "styling_plan": {"type": ["object", "null"]},
            "execution_steps": {"type": ["array", "null"], "items": {"type": "string"}},
            "agent_reasoning": {"type": ["string", "null"]},
            "audit_id": {"type": ["string", "null"]},
            "diagram_id": {"type": ["string", "null"]},
            "diagram_type": {"type": ["string", "null"]},
            "rendererInputAfter": {"type": ["string", "null"]},
            "svgAfter": {"type": ["string", "null"]},
            "auditId": {"type": ["string", "null"]},
            "file_path": {"type": ["string", "null"]},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "rendering_service": {"type": ["string", "null"]},
        }
    },
    side_effects="writes styling audits",
    handler=tool_svg_styling_agent,
    tool_id="svg_styling_agent",
    version="v1",
    mode="hybrid",
    metadata={"modes": ["pre-svg", "post-svg"], "returns": ["renderer_text", "svg", "audit_id"]},
)

STYLING_PRE_SVG_TOOL = MCPTool(
    name="styling.apply_pre_svg",
    description="Modify renderer input before SVG generation; returns rendererInputAfter and auditId",
    input_schema={
        "type": "object",
        "properties": {
            "diagramId": {"type": ["string", "null"]},
            "sessionId": {"type": ["string", "null"]},
            "userPrompt": {"type": ["string", "null"]},
            "rendererInput": {"type": ["string", "object"]},
            "renderer": {"type": ["string", "null"]},
            "diagramType": {"type": ["string", "null"]},
            "stylingIntent": {"type": ["string", "object", "null"]},
            "targetEngine": {"type": ["string", "null"]},
            "irId": {"type": ["string", "null"]},
            "mode": {"type": ["string", "null"]},
            "planId": {"type": ["string", "null"]},
            "renderingService": {"type": ["string", "null"]},
            "llmDiagram": {"type": ["object", "string", "null"]},
        },
        "required": ["rendererInput", "userPrompt"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "rendererInputAfter": {"type": ["string", "null"]},
            "renderer": {"type": ["string", "null"]},
            "auditId": {"type": ["string", "null"]},
            "mode": {"type": ["string", "null"]},
            "diagram_id": {"type": ["string", "null"]},
            "diagram_type": {"type": ["string", "null"]},
            "file_path": {"type": ["string", "null"]},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
    },
    side_effects="writes styling audits",
    handler=tool_apply_pre_svg_styling,
    tool_id="styling.apply_pre_svg",
    version="v1",
    mode="pre-svg",
    metadata={"returns": ["rendererInputAfter", "auditId"]},
)

STYLING_POST_SVG_TOOL = MCPTool(
    name="styling.apply_post_svg",
    description="Apply styling directly to rendered SVG content; returns svgAfter and auditId",
    input_schema={
        "type": "object",
        "properties": {
            "diagramId": {"type": ["string", "null"]},
            "sessionId": {"type": ["string", "null"]},
            "userPrompt": {"type": ["string", "null"]},
            "svgText": {"type": "string"},
            "diagramType": {"type": ["string", "null"]},
            "stylingIntent": {"type": ["string", "object", "null"]},
            "irId": {"type": ["string", "null"]},
            "mode": {"type": ["string", "null"]},
            "planId": {"type": ["string", "null"]},
            "renderingService": {"type": ["string", "null"]},
            "llmDiagram": {"type": ["object", "string", "null"]},
        },
        "required": ["svgText", "userPrompt"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "svgAfter": {"type": ["string", "null"]},
            "auditId": {"type": ["string", "null"]},
            "mode": {"type": ["string", "null"]},
            "diagram_id": {"type": ["string", "null"]},
            "diagram_type": {"type": ["string", "null"]},
            "file_path": {"type": ["string", "null"]},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
    },
    side_effects="writes styling audits",
    handler=tool_apply_post_svg_styling,
    tool_id="styling.apply_post_svg",
    version="v1",
    mode="post-svg",
    metadata={"returns": ["svgAfter", "auditId"]},
)

def tool_extract_text(context: Dict[str, Any], files: Iterable[str] | None = None, text: str | None = None) -> Dict[str, Any]:
    content = extract_text(files=files, text=text)
    return {"content": content}


def tool_generate_architecture_plan(context: Dict[str, Any], content: str) -> Dict[str, Any]:
    if not content or not content.strip():
        raise ValueError("content is required")
    plan = generate_architecture_plan_from_text(content, context=context)
    return {"architecture_plan": plan}


def tool_generate_plantuml(
    context: Dict[str, Any],
    architecture_plan: Dict[str, Any] | None,
    output_name: str,
    llm_diagram: str | None = None,
    diagram_type: str | None = None,
    format: str | None = None,
) -> Dict[str, Any]:
    if not output_name:
        raise ValueError("output_name is required")

    plan_id = context.get("plan_id")
    diagrams: List[Dict[str, Any]]
    if llm_diagram:
        diagrams = [
            {
                "type": (diagram_type or "diagram"),
                "llm_diagram": llm_diagram,
                "format": format or "plantuml",
                "plan_id": plan_id,
            }
        ]
    else:
        if not architecture_plan:
            raise ValueError("architecture_plan is required when llm_diagram is not provided")
        plan = ArchitecturePlan.parse_obj(architecture_plan)
        diagrams = generate_plantuml_from_plan(plan)
        if plan_id:
            for entry in diagrams:
                entry.setdefault("plan_id", plan_id)

    files = render_diagrams(
        diagrams,
        output_name,
        output_format="svg",
        audit_context=_build_render_audit_context(context),
    )
    ir_entries: list[dict[str, Any]] = []
    for file_path, diagram in zip(files, diagrams):
        try:
            svg_text = read_text_file(file_path)
        except Exception:
            svg_text = None
        if not svg_text:
            continue
        diagram_type_value = diagram.get("type") or _infer_diagram_type_from_path(file_path) or "diagram"
        diagram_format = diagram.get("format") or (diagram.get("llm_diagram") or {}).get("format")
        rendering_service = "mermaid" if str(diagram_format).lower().startswith("mermaid") else "plantuml"
        ir_entries.append({
            "diagram_type": diagram_type_value,
            "svg": svg_text,
            "svg_file": file_path,
            "reason": "PlantUML render",
            "rendering_service": rendering_service,
        })
    return {"files": files, "ir_entries": ir_entries}


def tool_generate_diagram(
    context: Dict[str, Any],
    architecture_plan: Dict[str, Any],
    output_name: str,
    diagram_type: str,
    overrides: Dict[str, Any] | None = None,
    rendering_service: str | None = None,
) -> Dict[str, Any]:
    if not architecture_plan:
        raise ValueError("architecture_plan is required")
    if not diagram_type:
        raise ValueError("diagram_type is required")
    plan = ArchitecturePlan.parse_obj(architecture_plan)
    plan_id = context.get("plan_id")
    provider = _resolve_render_provider(plan, diagram_type, rendering_service)
    audit_context = _build_render_audit_context(context)
    if provider == "mermaid":
        renderer_ir = _build_renderer_ir_from_plan(plan, diagram_type, overrides=overrides)
        diagram_text = _llm_generate_mermaid_from_ir(
            renderer_ir,
            diagram_type=diagram_type,
            plan=plan,
            context=context,
        )
        diagrams = [{
            "type": diagram_type,
            "llm_diagram": {"format": "mermaid", "diagram": diagram_text, "schema_version": 1},
            "format": "mermaid",
            "schema_version": 1,
        }]
    elif provider == "structurizr":
        renderer_ir = _build_renderer_ir_from_plan(plan, diagram_type, overrides=overrides)
        dsl_text = ir_to_structurizr_dsl(renderer_ir)
        svg_text = render_structurizr_svg(dsl_text)
        svg_file = render_ir_svg(svg_text, output_name)
        diagrams = [{
            "type": diagram_type,
            "svg": svg_text,
            "svg_file": svg_file,
            "format": "structurizr",
        }]
    else:
        diagrams = generate_plantuml_from_plan(plan, overrides=overrides, diagram_types=[diagram_type])
    if plan_id:
        for entry in diagrams:
            entry.setdefault("plan_id", plan_id)
    files: List[str]
    if diagrams and diagrams[0].get("svg"):
        files = [diagrams[0].get("svg_file")]
    else:
        files = render_diagrams(
            diagrams,
            output_name,
            output_format="svg",
            audit_context=audit_context,
        )
    ir_entries: list[dict[str, Any]] = []
    for file_path, diagram in zip(files, diagrams):
        try:
            svg_text = read_text_file(file_path)
        except Exception:
            svg_text = None
        if not svg_text:
            continue
        ir_entries.append(
            {
                "diagram_type": diagram.get("type", diagram_type),
                "svg": svg_text,
                "svg_file": file_path,
                "reason": overrides.get("reason") if overrides else None,
                "rendering_service": provider,
            }
        )
    return {"ir_entries": ir_entries}


def tool_generate_multiple_diagrams(
    context: Dict[str, Any],
    architecture_plan: Dict[str, Any],
    output_name: str,
    diagram_types: List[str] | None = None,
    rendering_service: str | None = None,
) -> Dict[str, Any]:
    if not architecture_plan:
        raise ValueError("architecture_plan is required")
    plan = ArchitecturePlan.parse_obj(architecture_plan)
    requested_types = diagram_types or list(plan.diagram_views)
    if not requested_types:
        requested_types = [settings.default_diagram_type]
    diagrams: List[Dict[str, Any]] = []
    per_type_provider = (rendering_service or "").lower().strip() if rendering_service else "auto"
    for diagram_type in requested_types:
        provider = _resolve_render_provider(plan, diagram_type, per_type_provider)
        if provider == "mermaid":
            renderer_ir = _build_renderer_ir_from_plan(plan, diagram_type)
            diagram_text = _llm_generate_mermaid_from_ir(
                renderer_ir,
                diagram_type=diagram_type,
                plan=plan,
                context=context,
            )
            diagrams.append({
                "type": diagram_type,
                "llm_diagram": {"format": "mermaid", "diagram": diagram_text, "schema_version": 1},
                "format": "mermaid",
                "schema_version": 1,
            })
        elif provider == "structurizr":
            renderer_ir = _build_renderer_ir_from_plan(plan, diagram_type)
            dsl_text = ir_to_structurizr_dsl(renderer_ir)
            svg_text = render_structurizr_svg(dsl_text)
            svg_file = render_ir_svg(svg_text, f"{output_name}_{diagram_type}")
            diagrams.append({
                "type": diagram_type,
                "svg": svg_text,
                "svg_file": svg_file,
                "format": "structurizr",
            })
        else:
            diagrams.extend(generate_plantuml_from_plan(plan, diagram_types=[diagram_type]))
    plan_id = context.get("plan_id")
    if plan_id:
        for entry in diagrams:
            entry.setdefault("plan_id", plan_id)
    struct_diagrams = [d for d in diagrams if d.get("svg")]
    non_struct_diagrams = [d for d in diagrams if not d.get("svg")]
    entries: list[dict[str, Any]] = []
    if non_struct_diagrams:
        files = render_diagrams(
            non_struct_diagrams,
            output_name,
            output_format="svg",
            audit_context=_build_render_audit_context(context),
        )
        for file_path, diagram in zip(files, non_struct_diagrams):
            try:
                svg_text = read_text_file(file_path)
            except Exception:
                svg_text = None
            if not svg_text:
                continue
            entries.append(
                {
                    "diagram_type": diagram.get("type"),
                    "svg": svg_text,
                    "svg_file": file_path,
                    "rendering_service": ("mermaid" if (diagram.get("format") or "").lower().startswith("mermaid") else "plantuml"),
                }
            )
    for diagram in struct_diagrams:
        svg_text = diagram.get("svg")
        svg_file = diagram.get("svg_file")
        if not svg_text or not svg_file:
            continue
        entries.append(
            {
                "diagram_type": diagram.get("type"),
                "svg": svg_text,
                "svg_file": svg_file,
                "rendering_service": "structurizr",
            }
        )
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
    rows = (
        db.query(Image)
        .filter(Image.session_id == _parse_uuid(session_id))
        .order_by(Image.version)
        .all()
    )
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


def tool_generate_sequence_from_architecture(
    context: Dict[str, Any],
    architecture_plan: Dict[str, Any],
    github_url: Optional[str] = None,
    user_message: Optional[str] = None,
    output_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a sequence diagram from architecture plan using LLM.
    
    Args:
        architecture_plan: The architecture plan dict
        github_url: Optional GitHub URL for context
        user_message: Optional user message for context
        output_name: Optional output name for file
        
    Returns:
        Dict with ir_entries containing the generated sequence diagram
    """
    if not architecture_plan:
        raise ValueError("architecture_plan is required")
    
    agent = SequenceGenerationAgent()
    sequence_data = agent.generate(
        architecture_plan=architecture_plan,
        github_url=github_url,
        user_message=user_message,
    )
    
    # Convert to StructuralIR format
    from src.intent.semantic_ir_sequence import SequenceSemanticIR, SequenceParticipant, SequenceStep
    from src.intent.semantic_to_structural import sequence_to_structural
    from src.renderers.router import render_ir
    from src.tools.svg_ir import render_ir_svg
    
    participants: list[SequenceParticipant] = []
    for idx, participant in enumerate(sequence_data.get("participants", []) or []):
        participant_id = str(participant.get("id") or f"participant_{idx+1}")
        label = str(participant.get("label") or participant.get("name") or participant_id)
        participants.append(SequenceParticipant(id=participant_id, label=label))

    steps: list[SequenceStep] = []
    for idx, step in enumerate(sequence_data.get("steps", []) or []):
        from_id = step.get("from") or step.get("from_id")
        to_id = step.get("to") or step.get("to_id")
        if not from_id or not to_id:
            # Skip malformed entries rather than failing the entire tool call
            continue
        step_id = str(step.get("id") or f"step_{idx+1}")
        order = step.get("order") or idx + 1
        steps.append(
            SequenceStep(
                id=step_id,
                from_=str(from_id),
                to=str(to_id),
                message=step.get("message"),
                order=int(order),
            )
        )
    
    semantic_ir = SequenceSemanticIR(
        title=sequence_data.get("title", "Sequence Diagram"),
        participants=participants,
        steps=steps,
    )
    
    structural_ir = sequence_to_structural(semantic_ir)
    svg_text, choice = render_ir(structural_ir)
    
    # Add metadata
    from src.services.session_service import _ensure_ir_metadata
    svg_text = _ensure_ir_metadata(svg_text, {
        "diagram_type": "sequence",
        "layout": structural_ir.layout,
        "zone_order": [],
        "nodes": [],
        "edges": [],
    })
    
    if output_name:
        svg_file = render_ir_svg(svg_text, output_name)
    else:
        svg_file = None
    
    return {
        "ir_entries": [{
            "diagram_type": "sequence",
            "svg": svg_text,
            "svg_file": svg_file,
            "reason": "Generated from architecture context",
            "rendering_service": choice.renderer,
        }]
    }


def tool_generate_plantuml_sequence(
    context: Dict[str, Any],
    architecture_plan: Dict[str, Any],
    output_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a PlantUML sequence diagram via the llm validation pipeline."""
    if not architecture_plan:
        raise ValueError("architecture_plan is required")
    
    # Generate PlantUML text
    plantuml_text = generate_plantuml_sequence_from_architecture(architecture_plan)
    output_label = output_name or "sequence"
    render_payload = render_llm_plantuml(plantuml_text, output_label, diagram_type="sequence")

    svg_path = render_payload["file_path"]
    try:
        svg_text = read_text_file(str(Path(svg_path)))
    except Exception:
        svg_text = Path(svg_path).read_text(encoding="utf-8", errors="ignore")

    return {
        "ir_entries": [
            {
                "diagram_type": "sequence",
                "svg": svg_text,
                "svg_file": svg_path,
                "plantuml_text": render_payload.get("sanitized_text"),
                "reason": "PlantUML sequence from architecture",
                "rendering_service": "plantuml",
            }
        ]
    }


def tool_mermaid_renderer(
    context: Dict[str, Any],
    ir: Dict[str, Any] | None = None,
    diagram_text: str | None = None,
    output_name: str | None = None,
) -> Dict[str, Any]:
    target_name = output_name or "mermaid_diagram"
    if not diagram_text:
        if not ir:
            raise ValueError("ir is required when diagram_text is not provided")
        renderer_ir = RendererIR.parse_obj(ir)
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for LLM Mermaid generation")
        diagram_text = _llm_generate_mermaid_from_ir(
            renderer_ir,
            diagram_type=str(renderer_ir.diagram_kind or "diagram"),
            plan=ArchitecturePlan.parse_obj({
                "system_name": "Generated",
                "diagram_views": ["diagram"],
                "zones": {
                    "clients": [],
                    "edge": [],
                    "core_services": [],
                    "external_services": [],
                    "data_stores": [],
                },
                "relationships": [],
                "visual_hints": {"layout": renderer_ir.layout, "group_by_zone": False, "external_dashed": True},
                "diagram_kind": renderer_ir.diagram_kind,
            }),
            context=context,
        )

    payload = render_llm_mermaid(diagram_text, target_name)
    return {
        "svg": payload["svg_text"],
        "file_path": payload["file_path"],
        "source_path": payload.get("source_path"),
        "warnings": payload.get("warnings") or [],
    }


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
        client = get_openai_client()
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
                svg_text = read_text_file(str(Path(image.file_path)))
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
    registry.register(SVG_STYLING_TOOL)
    registry.register(STYLING_PRE_SVG_TOOL)
    registry.register(STYLING_POST_SVG_TOOL)
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
            description="Renders PlantUML diagrams from either an architecture plan or an LLM-supplied PlantUML string.",
            input_schema={
                "type": "object",
                "properties": {
                    "architecture_plan": {"type": "object"},
                    "output_name": {"type": "string"},
                    "llm_diagram": {"type": "string"},
                    "diagram_type": {"type": ["string", "null"]},
                    "format": {"type": ["string", "null"]},
                },
                "required": ["output_name"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "files": {"type": "array", "items": {"type": "string"}},
                    "ir_entries": {"type": "array"},
                },
            },
            side_effects="writes diagram files",
            handler=tool_generate_plantuml,
        )
    )
    registry.register(
        MCPTool(
            name="generate_diagram",
            description="Generates a specific diagram type from an architecture plan.",
            input_schema={"type": "object", "properties": {"architecture_plan": {"type": "object"}, "output_name": {"type": "string"}, "diagram_type": {"type": "string"}, "rendering_service": {"type": ["string", "null"]}}, "required": ["architecture_plan", "output_name", "diagram_type"]},
            output_schema={"type": "object", "properties": {"ir_entries": {"type": "array"}}},
            side_effects="writes diagram files",
            handler=tool_generate_diagram,
        )
    )
    registry.register(
        MCPTool(
            name="generate_multiple_diagrams",
            description="Generates multiple diagrams from an architecture plan.",
            input_schema={"type": "object", "properties": {"architecture_plan": {"type": "object"}, "output_name": {"type": "string"}, "diagram_types": {"type": "array", "items": {"type": "string"}}, "rendering_service": {"type": ["string", "null"]}}, "required": ["architecture_plan", "output_name"]},
            output_schema={"type": "object", "properties": {"ir_entries": {"type": "array"}}},
            side_effects="writes diagram files",
            handler=tool_generate_multiple_diagrams,
        )
    )
    registry.register(
        MCPTool(
            name="mermaid_renderer",
            description="Render Mermaid diagrams either from renderer IR or direct Mermaid text (LLM default).",
            input_schema={
                "type": "object",
                "properties": {
                    "ir": {"type": "object"},
                    "diagram_text": {"type": "string"},
                    "output_name": {"type": "string"},
                },
                "required": [],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "svg": {"type": "string"},
                    "file_path": {"type": ["string", "null"]},
                    "source_path": {"type": ["string", "null"]},
                    "warnings": {"type": "array", "items": {"type": "string"}},
                },
            },
            side_effects="writes diagram files",
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
    registry.register(
        MCPTool(
            name="generate_sequence_from_architecture",
            description="Generate a meaningful sequence diagram from an architecture plan. Uses LLM to create realistic interaction flows based on the systems, services, and relationships in the architecture.",
            input_schema={
                "type": "object",
                "properties": {
                    "architecture_plan": {"type": "object"},
                    "github_url": {"type": "string"},
                    "user_message": {"type": "string"},
                    "output_name": {"type": "string"},
                },
                "required": ["architecture_plan"],
            },
            output_schema={"type": "object", "properties": {"ir_entries": {"type": "array"}}},
            side_effects="writes diagram files",
            handler=tool_generate_sequence_from_architecture,
        )
    )
    registry.register(
        MCPTool(
            name="generate_plantuml_sequence",
            description="Generate PlantUML sequence diagram directly from architecture plan. Fast, no LLM needed, works every time.",
            input_schema={
                "type": "object",
                "properties": {
                    "architecture_plan": {"type": "object"},
                    "output_name": {"type": "string"},
                },
                "required": ["architecture_plan"],
            },
            output_schema={"type": "object", "properties": {"ir_entries": {"type": "array"}}},
            side_effects="writes diagram files",
            handler=tool_generate_plantuml_sequence,
        )
    )
