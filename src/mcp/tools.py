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
from src.services.agent_trace_service import record_trace
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
    r"(?<!\w)(#[0-9a-fA-F]{3,8}|" + "|".join(sorted({c for c in _COLOR_ALIASES}, key=len, reverse=True)) + r")\b",
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

    # Detect explicit "X background" / "background X" pattern first
    bg_match = re.search(
        r"(?:(\w+)\s+background|background\s+(?:color\s+)?(?:is\s+|=\s*)?(\w+))",
        lowered,
    )
    bg_color_word: str | None = None
    if bg_match:
        bg_color_word = (bg_match.group(1) or bg_match.group(2) or "").strip()
        resolved_bg = _resolve_color(bg_color_word)
        if resolved_bg != "#333333":  # valid color
            intent["blockColors"]["background"] = resolved_bg

    found_colors: list[str] = []
    for match in _COLOR_PATTERN.findall(text):
        normalized = _resolve_color(match)
        # Skip colors already assigned as background
        if bg_color_word and match.lower() == bg_color_word.lower():
            continue
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
    if block_colors.get("background"):
        theme_vars["background"] = _resolve_color(block_colors["background"])
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


def apply_ir_node_styles_to_svg(svg_text: str, ir_json: dict) -> str:
    """Apply per-node styling from the IR's node_style fields to the SVG.

    This bridges the gap between the IR data model (which carries per-node
    fillColor, borderColor, textColor, shape, etc.) and the rendered SVG
    (which may come from Mermaid-cli, custom IR renderer, or PlantUML).

    Works with BOTH SVG flavours:
    - Custom IR renderer: nodes have ``data-block-id="<node_id>"`` on ``<g>``
      groups, child ``<rect class="node-rect">`` and ``<text class="node-text">``.
    - Mermaid-cli: nodes have ``id="flowchart-<slug>-<n>"`` on ``<g class="node
      default">`` groups, child ``<rect class="basic label-container">``.

    Returns the modified SVG string.
    """
    # Navigate into enriched_ir when nodes are nested (real DB IR structure)
    _inner = ir_json.get("enriched_ir") if isinstance(ir_json.get("enriched_ir"), dict) else None
    nodes = ir_json.get("nodes") or (_inner.get("nodes") if _inner else None) or []
    if not nodes:
        return svg_text

    # Build a lookup: node_id -> node_style dict, and node_id -> shape
    style_map: dict[str, dict] = {}
    label_map: dict[str, dict] = {}
    shape_map: dict[str, str] = {}
    for node in nodes:
        nid = str(node.get("node_id") or node.get("id") or "")
        style = node.get("node_style") or {}
        if nid and style:
            style_map[nid] = style
        label = str(node.get("label") or "").strip()
        if label and style:
            label_map[label.lower()] = style
        # Track shape for geometry changes (circle, diamond, cylinder, etc.)
        node_shape = str(node.get("shape") or "").strip().lower()
        if nid and node_shape:
            shape_map[nid] = node_shape

    if not style_map and not label_map and not shape_map:
        return svg_text

    try:
        parser = ET.XMLParser(encoding="utf-8")
        root = ET.fromstring(svg_text.encode("utf-8"), parser=parser)
    except Exception:
        return svg_text

    # Strategy 1: Custom IR renderer — groups with data-block-id attribute
    for group in root.iter():
        block_id = group.get("data-block-id")
        if not block_id:
            continue
        style = style_map.get(block_id)
        if style:
            _apply_style_to_group(group, style)
        target_shape = shape_map.get(block_id)
        if target_shape:
            _replace_shape_in_group(group, target_shape)

    # Strategy 2: Mermaid-cli — groups with class containing "node" and
    # id like "flowchart-<slug>-<n>".  Match by mapping node labels to
    # the text content inside each group.
    SVG_NS = "{http://www.w3.org/2000/svg}"
    XHTML_NS = "{http://www.w3.org/1999/xhtml}"
    for group in root.iter():
        cls = group.get("class", "")
        if "node" not in cls.split():
            continue
        # Extract label text from this Mermaid node group
        node_text = _extract_mermaid_node_text(group, SVG_NS, XHTML_NS)
        if not node_text:
            continue
        # Match against label_map
        style = label_map.get(node_text.lower())
        if not style:
            # fuzzy: try partial match
            for lbl, s in label_map.items():
                if lbl in node_text.lower() or node_text.lower() in lbl:
                    style = s
                    break
        if style:
            _apply_style_to_mermaid_node(group, style, SVG_NS, XHTML_NS)

    try:
        return ET.tostring(root, encoding="unicode")
    except Exception:
        return svg_text


def _extract_mermaid_node_text(group, SVG_NS: str, XHTML_NS: str) -> str:
    """Extract the visible label text from a Mermaid node <g> group."""
    # Try foreignObject -> span.nodeLabel
    for fo in group.iter(f"{SVG_NS}foreignObject"):
        for span in fo.iter(f"{XHTML_NS}span"):
            if "nodeLabel" in (span.get("class") or ""):
                txt = "".join(span.itertext()).strip()
                if txt:
                    return txt
        # Also check raw div/p text
        for div in fo.iter(f"{XHTML_NS}div"):
            txt = "".join(div.itertext()).strip()
            if txt:
                return txt
    # Fallback: SVG <text> element
    for t in group.iter(f"{SVG_NS}text"):
        txt = "".join(t.itertext()).strip()
        if txt:
            return txt
    # Last resort: any text
    for t in group.iter():
        if t.tag.endswith("text"):
            txt = "".join(t.itertext()).strip()
            if txt:
                return txt
    return ""


def _replace_shape_in_group(group, target_shape: str):
    """Replace the geometry element inside a custom-IR-renderer <g> group.

    Supported target shapes: circle, ellipse, diamond, hexagon, cylinder, rect/rounded.
    The original <rect class="node-rect"> is replaced with an SVG element that
    visually represents the requested shape, preserving position and size.
    """
    # Find the existing shape element (rect, circle, ellipse, etc.)
    existing = None
    existing_idx = None
    for idx, child in enumerate(group):
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag in ("rect", "circle", "ellipse", "polygon", "path") and "node-rect" in (child.get("class") or tag):
            existing = child
            existing_idx = idx
            break
    if existing is None:
        # fallback: grab first shape element
        for idx, child in enumerate(group):
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag in ("rect", "circle", "ellipse", "polygon", "path"):
                existing = child
                existing_idx = idx
                break
    if existing is None or existing_idx is None:
        return

    # Extract geometry from the existing element
    tag = existing.tag.split("}")[-1] if "}" in existing.tag else existing.tag
    ns_prefix = existing.tag[: existing.tag.index("}") + 1] if "}" in existing.tag else ""
    fill = existing.get("fill", "none")
    stroke = existing.get("stroke", "#64748b")
    stroke_width = existing.get("stroke-width", "1")
    stroke_dash = existing.get("stroke-dasharray")
    elem_class = existing.get("class", "")
    elem_id = existing.get("id", "")

    if tag == "rect":
        x = float(existing.get("x", 0))
        y = float(existing.get("y", 0))
        w = float(existing.get("width", 140))
        h = float(existing.get("height", 48))
    elif tag == "circle":
        cx = float(existing.get("cx", 70))
        cy = float(existing.get("cy", 24))
        r = float(existing.get("r", 24))
        x, y, w, h = cx - r, cy - r, r * 2, r * 2
    elif tag == "ellipse":
        cx = float(existing.get("cx", 70))
        cy = float(existing.get("cy", 24))
        rx = float(existing.get("rx", 70))
        ry = float(existing.get("ry", 24))
        x, y, w, h = cx - rx, cy - ry, rx * 2, ry * 2
    else:
        x, y, w, h = 0, 0, 140, 48

    cx, cy = x + w / 2, y + h / 2

    # Current shape already matches target?
    _SHAPE_TAG = {
        "circle": "circle", "ellipse": "ellipse", "oval": "ellipse",
        "rect": "rect", "rectangle": "rect", "rounded": "rect", "box": "rect", "square": "rect",
        "diamond": "polygon", "hexagon": "polygon",
        "cylinder": "ellipse",
    }
    target_tag = _SHAPE_TAG.get(target_shape, target_shape)
    if target_tag == tag and target_shape not in ("diamond", "hexagon", "cylinder"):
        return  # already correct shape

    # Build replacement element
    new_elem = None
    if target_shape == "circle":
        r = min(w, h) / 2
        new_elem = ET.Element(f"{ns_prefix}circle" if ns_prefix else "circle")
        new_elem.set("cx", str(cx))
        new_elem.set("cy", str(cy))
        new_elem.set("r", str(r))
    elif target_shape in ("ellipse", "oval"):
        new_elem = ET.Element(f"{ns_prefix}ellipse" if ns_prefix else "ellipse")
        new_elem.set("cx", str(cx))
        new_elem.set("cy", str(cy))
        new_elem.set("rx", str(w / 2))
        new_elem.set("ry", str(h / 2))
    elif target_shape == "diamond":
        points = f"{cx},{y} {x + w},{cy} {cx},{y + h} {x},{cy}"
        new_elem = ET.Element(f"{ns_prefix}polygon" if ns_prefix else "polygon")
        new_elem.set("points", points)
    elif target_shape == "hexagon":
        dx = w * 0.2
        points = f"{x + dx},{y} {x + w - dx},{y} {x + w},{cy} {x + w - dx},{y + h} {x + dx},{y + h} {x},{cy}"
        new_elem = ET.Element(f"{ns_prefix}polygon" if ns_prefix else "polygon")
        new_elem.set("points", points)
    elif target_shape == "cylinder":
        # Approximate with an ellipse (visual shorthand for database shape)
        new_elem = ET.Element(f"{ns_prefix}ellipse" if ns_prefix else "ellipse")
        new_elem.set("cx", str(cx))
        new_elem.set("cy", str(cy))
        new_elem.set("rx", str(w / 2))
        new_elem.set("ry", str(h / 2))
    else:
        # Default: rect (covers rect, rounded, box, square)
        new_elem = ET.Element(f"{ns_prefix}rect" if ns_prefix else "rect")
        new_elem.set("x", str(x))
        new_elem.set("y", str(y))
        new_elem.set("width", str(w))
        new_elem.set("height", str(h))
        if target_shape == "rounded":
            new_elem.set("rx", "8")
            new_elem.set("ry", "8")

    if new_elem is None:
        return

    # Carry over visual attributes
    new_elem.set("fill", fill)
    new_elem.set("stroke", stroke)
    new_elem.set("stroke-width", stroke_width)
    if stroke_dash:
        new_elem.set("stroke-dasharray", stroke_dash)
    if elem_class:
        new_elem.set("class", elem_class)
    if elem_id:
        new_elem.set("id", elem_id)

    # Replace the old element in the group
    group.remove(existing)
    group.insert(existing_idx, new_elem)


def _apply_style_to_group(group, style: dict):
    """Apply IR node_style to a custom-IR-renderer SVG <g> group."""
    for child in group:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag in ("rect", "circle", "ellipse", "polygon", "path"):
            if style.get("fillColor"):
                child.set("fill", _resolve_color(style["fillColor"]))
            if style.get("borderColor"):
                child.set("stroke", _resolve_color(style["borderColor"]))
            if style.get("borderWidth"):
                child.set("stroke-width", str(style["borderWidth"]))
            if style.get("borderStyle") == "dashed":
                child.set("stroke-dasharray", "6,3")
            elif style.get("borderStyle") == "dotted":
                child.set("stroke-dasharray", "2,2")
            elif style.get("borderStyle") == "none":
                child.set("stroke", "none")
        elif tag == "text":
            if style.get("textColor"):
                child.set("fill", _resolve_color(style["textColor"]))
            if style.get("fontSize"):
                child.set("font-size", str(style["fontSize"]))
            if style.get("fontFamily"):
                child.set("font-family", style["fontFamily"])


def _apply_style_to_mermaid_node(group, style: dict, SVG_NS: str, XHTML_NS: str):
    """Apply IR node_style to a Mermaid-cli SVG node <g> group."""
    # Shape elements: rect, circle, polygon, path inside the node group
    for child in group:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        cls = child.get("class", "")
        # Mermaid node shapes have class like "basic label-container"
        if tag in ("rect", "circle", "ellipse", "polygon", "path") and "label" not in cls:
            if style.get("fillColor"):
                child.set("fill", _resolve_color(style["fillColor"]))
            if style.get("borderColor"):
                child.set("stroke", _resolve_color(style["borderColor"]))
            if style.get("borderWidth"):
                child.set("stroke-width", str(style["borderWidth"]))
        # Rects with "basic label-container" are the main shape in Mermaid
        if tag == "rect" and "label-container" in cls:
            if style.get("fillColor"):
                child.set("fill", _resolve_color(style["fillColor"]))
                child.set("style", f"fill: {_resolve_color(style['fillColor'])} !important;")
            if style.get("borderColor"):
                child.set("stroke", _resolve_color(style["borderColor"]))
    # Text color in Mermaid uses foreignObject -> span
    if style.get("textColor"):
        tc = _resolve_color(style["textColor"])
        for fo in group.iter(f"{SVG_NS}foreignObject"):
            for span in fo.iter(f"{XHTML_NS}span"):
                existing = span.get("style", "")
                span.set("style", f"{existing}; color: {tc} !important;")
        for t in group.iter(f"{SVG_NS}text"):
            t.set("fill", tc)


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

    # Detect SVG id for scoped selectors (Mermaid uses id="my-svg")
    svg_id = root.get("id", "")
    prefix = f"#{svg_id} " if svg_id else ""

    style_rules: list[str] = []

    # Background color (third found color or explicit request)
    bg_color = intent.get("blockColors", {}).get("background")
    if bg_color:
        style_rules.append(f"{prefix.strip() or 'svg'} {{ background-color: {_resolve_color(bg_color)} !important; }}")

    # Block colors -> apply to node shapes in both Mermaid-cli and custom IR SVGs
    primary = intent.get("blockColors", {}).get("primary")
    secondary = intent.get("blockColors", {}).get("secondary")
    if primary:
        pc = _resolve_color(primary)
        # Mermaid-cli: node shapes are rect/circle/ellipse/polygon/path inside .node groups
        style_rules.append(f"{prefix}.node rect, {prefix}.node circle, {prefix}.node ellipse, "
                           f"{prefix}.node polygon, {prefix}.node path {{ fill: {pc} !important; }}")
        # Mermaid sequence diagram actors
        style_rules.append(f"{prefix}.actor {{ fill: {pc} !important; }}")
        # Custom IR renderer fallback
        style_rules.append(f"{prefix}.node-rect {{ fill: {pc} !important; }}")
    if secondary:
        sc = _resolve_color(secondary)
        # Apply secondary color to every other node via nth-child
        style_rules.append(f"{prefix}.node:nth-child(even) rect, {prefix}.node:nth-child(even) circle, "
                           f"{prefix}.node:nth-child(even) ellipse, {prefix}.node:nth-child(even) polygon, "
                           f"{prefix}.node:nth-child(even) path {{ fill: {sc} !important; }}")
        style_rules.append(f"{prefix}.node-rect.secondary {{ fill: {sc} !important; }}")

    # Text styles — Mermaid uses both SVG <text> and HTML .nodeLabel spans
    txt = intent.get("textStyle", {})
    if txt.get("fontWeight"):
        style_rules.append(f"{prefix}text {{ font-weight: {txt['fontWeight']} !important; }}")
        style_rules.append(f"{prefix}.nodeLabel {{ font-weight: {txt['fontWeight']} !important; }}")
    if txt.get("fontColor"):
        fc = _resolve_color(txt["fontColor"])
        style_rules.append(f"{prefix}text {{ fill: {fc} !important; }}")
        # Mermaid flowchart labels use HTML inside foreignObject
        style_rules.append(f"{prefix}.nodeLabel, {prefix}.nodeLabel p {{ color: {fc} !important; }}")
        style_rules.append(f"{prefix}.edgeLabel, {prefix}.edgeLabel p {{ color: {fc} !important; }}")

    # Edge styles
    edge = intent.get("edgeStyle", {})
    if edge.get("strokeColor"):
        ec = _resolve_color(edge["strokeColor"])
        style_rules.append(f"{prefix}.flowchart-link, {prefix}.edgePath .path {{ stroke: {ec} !important; }}")
        style_rules.append(f"{prefix}.messageLine0, {prefix}.messageLine1 {{ stroke: {ec} !important; }}")
        # Arrowheads
        style_rules.append(f"{prefix}.arrowMarkerPath, {prefix}.arrowheadPath {{ fill: {ec} !important; stroke: {ec} !important; }}")
        # Fallback for generic SVG
        style_rules.append(f"path, line {{ stroke: {ec} !important; }}")
    if edge.get("strokeWidth"):
        style_rules.append(f"{prefix}.flowchart-link, {prefix}.edgePath .path {{ stroke-width: {edge['strokeWidth']} !important; }}")
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


def tool_styling_transform_agent(
    context: Dict[str, typing.Any],
    ir: typing.Optional[dict],
    user_edit_suggestion: typing.Optional[str] = None,
    mode: str = "style_only",
    constraints: typing.Optional[dict] = None,
) -> Dict[str, typing.Any]:
    """Pure transformation Styling Agent.

    Accepts the current `ir` (dictionary), a `user_edit_suggestion`, optional `mode` and `constraints`.
    Returns one of:
      - {"patch_ops": [...]} (preferred – minimalistic delta)
      - {"updated_ir": {...}} (fallback – full copy with minimal edits)
      - {"error": "...", "explanation": "..."}

    This implementation uses deterministic heuristics to interpret common edit
    suggestions.  It is intentionally **minimalistic**: it returns only the
    smallest set of patch_ops needed to honour the user's request and leaves
    every other field of the IR untouched.

    It does NOT perform side-effects and does not call Main Agent.
    """
    if ir is None:
        return {"error": "no_ir", "explanation": "No IR provided to styling agent"}

    suggestion = (user_edit_suggestion or "").strip()
    if not suggestion:
        return {"error": "no_suggestion", "explanation": "No edit suggestion provided"}

    lowered = suggestion.lower()

    # Navigate into enriched_ir when nodes/edges are nested (real DB IR structure)
    _inner = ir.get("enriched_ir") if isinstance(ir.get("enriched_ir"), dict) else None
    nodes = ir.get("nodes") or (_inner.get("nodes") if _inner else None) or []
    edges = ir.get("edges") or (_inner.get("edges") if _inner else None) or []
    patch_ops: list[dict] = []

    # ── helpers ────────────────────────────────────────────────────────────
    def _find_node(target: str):
        """Find a node whose label or id contains `target`."""
        target = target.strip().lower()
        for n in nodes:
            label = str(n.get("label") or "").lower()
            nid = str(n.get("node_id") or n.get("id") or "").lower()
            if target == label or target == nid:
                return n
        # fuzzy: substring
        for n in nodes:
            label = str(n.get("label") or "").lower()
            nid = str(n.get("node_id") or n.get("id") or "").lower()
            if target in label or target in nid:
                return n
        return None

    def _node_id(node: dict) -> str:
        return node.get("node_id") or node.get("id") or ""

    # ── 1.  Shape changes (circular, diamond, hexagon, rectangle …) ───────
    _SHAPE_KEYWORDS = {
        "circular": "circle", "circle": "circle", "round": "circle",
        "diamond": "diamond", "rhombus": "diamond",
        "hexagon": "hexagon", "hex": "hexagon",
        "rectangle": "rect", "rect": "rect", "square": "rect", "box": "rect",
        "cylinder": "cylinder", "database": "cylinder", "db": "cylinder",
        "ellipse": "ellipse", "oval": "ellipse",
    }
    for shape_kw, shape_val in _SHAPE_KEYWORDS.items():
        m = re.search(
            rf"make\s+(?:the\s+)?(.+?)\s+(?:block|node|component|service)?\s*{shape_kw}"
            rf"|make\s+(.+?)\s+{shape_kw}",
            lowered,
        )
        if m:
            target_name = (m.group(1) or m.group(2) or "").strip()
            matched = _find_node(target_name)
            if matched:
                nid = _node_id(matched)
                patch_ops.append({"op": "replace", "path": f"/nodes/{nid}/shape", "value": shape_val})
                return {"patch_ops": patch_ops}

    # ── 2.  Colour / color changes ────────────────────────────────────────
    m = re.search(
        r"(?:change|set|make|paint|color|colour)\s+(?:the\s+)?(.+?)\s+"
        r"(?:block|node|component|service)?\s*(?:color|colour)?\s*(?:to\s+)?\s*"
        r"(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)\s*$",
        lowered,
    )
    if m:
        target_name = m.group(1).strip()
        color_raw = m.group(2).strip()
        color_val = _resolve_color(color_raw)
        matched = _find_node(target_name)
        if matched:
            nid = _node_id(matched)
            patch_ops.append({"op": "replace", "path": f"/nodes/{nid}/node_style/fillColor", "value": color_val})
            return {"patch_ops": patch_ops}

    # ── 3.  Label / rename changes ────────────────────────────────────────
    m = re.search(
        r"(?:rename|relabel|change\s+(?:the\s+)?label\s+(?:of\s+)?)(?:the\s+)?(.+?)\s+(?:to|as|→|->)\s+(.+)",
        lowered,
    )
    if m:
        target_name = m.group(1).strip()
        new_label = m.group(2).strip()
        matched = _find_node(target_name)
        if matched:
            nid = _node_id(matched)
            # Keep the label case from the user (use original suggestion)
            raw_new = suggestion[m.start(2):m.end(2)].strip() or new_label
            patch_ops.append({"op": "replace", "path": f"/nodes/{nid}/label", "value": raw_new})
            return {"patch_ops": patch_ops}

    # ── 4.  Border / stroke style changes ─────────────────────────────────
    m = re.search(
        r"(?:make|set|change)\s+(?:the\s+)?(.+?)\s+(?:block|node)?\s*"
        r"(?:border|stroke|outline)\s*(?:to\s+|=\s*)?(dashed|dotted|solid|thick|thin|bold|none|\d+)",
        lowered,
    )
    if m:
        target_name = m.group(1).strip()
        style_val = m.group(2).strip()
        matched = _find_node(target_name)
        if matched:
            nid = _node_id(matched)
            if style_val in {"dashed", "dotted", "solid", "none"}:
                patch_ops.append({"op": "replace", "path": f"/nodes/{nid}/node_style/borderStyle", "value": style_val})
            elif style_val in {"thick", "bold"}:
                patch_ops.append({"op": "replace", "path": f"/nodes/{nid}/node_style/borderWidth", "value": 3})
            elif style_val == "thin":
                patch_ops.append({"op": "replace", "path": f"/nodes/{nid}/node_style/borderWidth", "value": 1})
            elif style_val.isdigit():
                patch_ops.append({"op": "replace", "path": f"/nodes/{nid}/node_style/borderWidth", "value": int(style_val)})
            if patch_ops:
                return {"patch_ops": patch_ops}

    # ── 5.  Hide / show a node ────────────────────────────────────────────
    m = re.search(r"(?:hide|remove|delete)\s+(?:the\s+)?(.+?)\s*(?:block|node|component|service)?", lowered)
    if m:
        target_name = m.group(1).strip()
        matched = _find_node(target_name)
        if matched:
            nid = _node_id(matched)
            patch_ops.append({"op": "replace", "path": f"/nodes/{nid}/node_style/visible", "value": False})
            return {"patch_ops": patch_ops}

    m = re.search(r"(?:show|unhide|reveal)\s+(?:the\s+)?(.+?)\s*(?:block|node|component|service)?", lowered)
    if m:
        target_name = m.group(1).strip()
        matched = _find_node(target_name)
        if matched:
            nid = _node_id(matched)
            patch_ops.append({"op": "replace", "path": f"/nodes/{nid}/node_style/visible", "value": True})
            return {"patch_ops": patch_ops}

    # ── 6.  Zone reorder ──────────────────────────────────────────────────
    zone_order = ir.get("zone_order") or []
    m_above = re.search(r"move\s+(.+?)\s+above\s+(.+)", lowered)
    m_below = re.search(r"move\s+(.+?)\s+below\s+(.+)", lowered)
    if m_above or m_below:
        match = m_above or m_below
        frag1 = match.group(1).strip()
        frag2 = match.group(2).strip()

        def _match_zone(fragment: str):
            for z in zone_order:
                if z.replace("_", " ") in fragment or z in fragment or fragment in z.replace("_", " "):
                    return z
            return None

        z1 = _match_zone(frag1)
        z2 = _match_zone(frag2)
        if z1 and z2 and z1 != z2:
            new_order = [z for z in zone_order if z not in {z1, z2}]
            if m_above:
                idx = 0
                new_order.insert(idx, z1)
                new_order.insert(idx + 1, z2)
            else:
                idx = 0
                new_order.insert(idx, z2)
                new_order.insert(idx + 1, z1)
            patch_ops.append({"op": "replace", "path": "/zone_order", "value": new_order})
            return {"patch_ops": patch_ops}

    # ── 7.  Global intent / theme tweaks ──────────────────────────────────
    for theme_kw in ("pastel", "dark", "vibrant", "minimal", "corporate"):
        if theme_kw in lowered and ("theme" in lowered or "style" in lowered or "look" in lowered or theme_kw == lowered.strip()):
            patch_ops.append({"op": "replace", "path": "/globalIntent/mood", "value": theme_kw})
            return {"patch_ops": patch_ops}

    # ── 8.  Edge colour / style ───────────────────────────────────────────
    m = re.search(
        r"(?:change|set|make)\s+(?:the\s+)?(?:edge|line|arrow|connection)s?\s*(?:color|colour)?\s*(?:to\s+)?"
        r"(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)",
        lowered,
    )
    if m:
        color_val = _resolve_color(m.group(1).strip())
        patch_ops.append({"op": "replace", "path": "/globalIntent/edgeColor", "value": color_val})
        return {"patch_ops": patch_ops}

    # ── If nothing matched, return controlled error ───────────────────────
    return {"error": "unhandled_suggestion", "explanation": "Styling agent could not interpret the suggestion deterministically"}


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
        try:
            ir = db.get(DiagramIR, _parse_uuid(ir_id))
        except Exception:
            ir = None
    if not ir and session_id:
        try:
            rows = db.query(DiagramIR).filter(DiagramIR.session_id == _parse_uuid(session_id)).order_by(DiagramIR.version.desc()).all()
            ir = rows[0] if rows else None
        except Exception:
            ir = None
    # Fallback: resolve session from context when both explicit lookups fail
    if not ir:
        ctx_session = context.get("session")
        ctx_session_id = context.get("session_id")
        fallback_sid = getattr(ctx_session, "id", None) or ctx_session_id
        if fallback_sid:
            try:
                rows = db.query(DiagramIR).filter(DiagramIR.session_id == _parse_uuid(str(fallback_sid))).order_by(DiagramIR.version.desc()).all()
                ir = rows[0] if rows else None
            except Exception:
                ir = None
    if not ir:
        raise ValueError("No IR version available to edit")
    # Build canonical IR payload to send to the Styling/Transformation Agent
    current_ir_json = ir.ir_json if getattr(ir, "ir_json", None) else None
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

    # Route edit intent to the Styling Transform Agent (pure, no side-effects)
    import time as _time
    _t0 = _time.perf_counter()
    transform_result = tool_styling_transform_agent(context=context, ir=current_ir_json, user_edit_suggestion=instruction)
    _transform_ms = int((_time.perf_counter() - _t0) * 1000)

    # ── Trace: styling transform agent decision ──
    _ctx_db = context.get("db")
    _ctx_sid = context.get("session_id") or (getattr(context.get("session"), "id", None))
    if _ctx_db and _ctx_sid:
        _transform_input = {
            "instruction": instruction,
            "ir_id": str(ir.id) if ir else None,
            "ir_node_count": len((current_ir_json or {}).get("enriched_ir", current_ir_json or {}).get("nodes", [])) if current_ir_json else 0,
        }
        _transform_out = {}
        if isinstance(transform_result, dict):
            if transform_result.get("patch_ops"):
                _transform_out["patch_ops_count"] = len(transform_result["patch_ops"])
                _transform_out["patch_ops"] = transform_result["patch_ops"]
            elif transform_result.get("updated_ir"):
                _transform_out["has_updated_ir"] = True
            elif transform_result.get("error"):
                _transform_out["error"] = transform_result["error"]
                _transform_out["explanation"] = transform_result.get("explanation")
        record_trace(
            _ctx_db,
            session_id=_ctx_sid,
            agent_name="styling_transform_agent",
            input_summary=_transform_input,
            output_summary=_transform_out,
            decision=("patch_ops" if (isinstance(transform_result, dict) and transform_result.get("patch_ops"))
                       else "updated_ir" if (isinstance(transform_result, dict) and transform_result.get("updated_ir"))
                       else transform_result.get("error", "unknown") if isinstance(transform_result, dict)
                       else "invalid"),
            duration_ms=_transform_ms,
        )

    # Validate contract and return structured result for the Main Agent to apply deterministically
    if not isinstance(transform_result, dict):
        return {"error": "invalid_response", "message": "Styling agent returned non-dict response"}

    # Allow the Main Agent (session_service) to handle patch_ops or updated_ir
    out: Dict[str, Any] = {}
    if transform_result.get("patch_ops"):
        out["patch_ops"] = transform_result.get("patch_ops")
        out["parent_ir_id"] = str(ir.id)
        out["diagram_type"] = ir.diagram_type
        out["svg"] = svg_text
    elif transform_result.get("updated_ir"):
        out["updated_ir"] = transform_result.get("updated_ir")
        out["parent_ir_id"] = str(ir.id)
        out["diagram_type"] = ir.diagram_type
        out["svg"] = svg_text
    else:
        # No structured patch provided.  Try to apply a minimal zone-reorder
        # via the legacy helper and then merge the reordered zone_order back
        # into the *existing* IR as a patch — avoiding a full SVG rebuild.
        import copy as _copy
        try:
            edited_svg = edit_ir_svg(svg_text, instruction)
            # Extract just the zone_order delta from the edited SVG metadata
            import xml.etree.ElementTree as _ET
            edited_root = _ET.fromstring(edited_svg)
            edited_meta = None
            for el in edited_root.iter():
                if el.tag.endswith("metadata") and el.text:
                    edited_meta = el
                    break
            if edited_meta is not None and edited_meta.text:
                edited_payload = json.loads(edited_meta.text)
                parent_ir_json = _copy.deepcopy(current_ir_json) if current_ir_json else {}
                new_zone_order = edited_payload.get("zone_order")
                old_zone_order = parent_ir_json.get("zone_order")
                if new_zone_order and new_zone_order != old_zone_order:
                    # Apply only the zone_order change to the existing full IR
                    parent_ir_json["zone_order"] = new_zone_order
                    out = {
                        "updated_ir": parent_ir_json,
                        "parent_ir_id": str(ir.id),
                        "diagram_type": ir.diagram_type,
                        "svg": svg_text,  # keep original SVG; will be re-rendered
                    }
                else:
                    # No zone change detected — use edited SVG but keep full IR
                    out = {
                        "svg": edited_svg,
                        "parent_ir_id": str(ir.id),
                        "diagram_type": ir.diagram_type,
                    }
            else:
                out = {"svg": edited_svg, "parent_ir_id": str(ir.id), "diagram_type": ir.diagram_type}
        except Exception:
            out = {
                "error": transform_result.get("error") or "no_change",
                "message": transform_result.get("explanation"),
            }

    return {"ir_entries": [out]}


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
