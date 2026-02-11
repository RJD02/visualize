"""Apply aesthetic plans to SVG content."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Set
from xml.etree import ElementTree as ET

from src.aesthetics.aesthetic_plan_schema import AestheticPlan
from src.animation.svg_structural_analyzer import SVGStructuralGraph, analyze_svg


SHAPE_TAGS = {"rect", "circle", "ellipse", "polygon", "path"}
EDGE_TAGS = {"path", "line", "polyline"}
TEXT_TAG = "text"


@dataclass(frozen=True)
class HighlightSelection:
    node_ids: Set[str]
    edge_ids: Set[str]


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _find_first_shape(el: ET.Element) -> Optional[ET.Element]:
    for child in el.iter():
        if _strip_ns(child.tag) in SHAPE_TAGS:
            return child
    return None


def _find_text_elements(el: ET.Element) -> Iterable[ET.Element]:
    for child in el.iter():
        if _strip_ns(child.tag) == TEXT_TAG:
            yield child


def _ensure_class(el: ET.Element, class_name: str) -> None:
    existing = el.get("class") or ""
    classes = [c for c in existing.split() if c]
    if class_name not in classes:
        classes.append(class_name)
    el.set("class", " ".join(classes))


def _set_style_attr(el: ET.Element, updates: Dict[str, str]) -> None:
    existing = el.get("style") or ""
    parts = [p.strip() for p in existing.split(";") if p.strip()]
    style_map: Dict[str, str] = {}
    for part in parts:
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        style_map[key.strip()] = value.strip()
    for key, value in updates.items():
        style_map[key] = value
    el.set("style", "; ".join(f"{k}: {v}" for k, v in style_map.items()))


def _get_luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _select_highlights(graph: SVGStructuralGraph) -> HighlightSelection:
    node_ids = [node.id for node in graph.nodes]
    if not node_ids:
        return HighlightSelection(node_ids=set(), edge_ids=set())

    degree: Dict[str, int] = {node_id: 0 for node_id in node_ids}
    for edge in graph.edges:
        if edge.source_id in degree:
            degree[edge.source_id] += 1
        if edge.target_id in degree:
            degree[edge.target_id] += 1

    sorted_nodes = sorted(node_ids, key=lambda nid: degree.get(nid, 0), reverse=True)
    if len(node_ids) <= 4:
        count = 2
    elif len(node_ids) <= 10:
        count = 2
    elif len(node_ids) <= 18:
        count = 3
    else:
        count = 2

    highlight_nodes = set(sorted_nodes[:count])
    active_edges = set()
    for edge in graph.edges:
        if edge.source_id in highlight_nodes or edge.target_id in highlight_nodes:
            active_edges.add(edge.id)

    return HighlightSelection(node_ids=highlight_nodes, edge_ids=active_edges)


def _build_css(plan: AestheticPlan) -> str:
    text_color = "#0f172a" if _get_luminance(plan.background) > 0.6 else "#f8fafc"
    node_default = plan.nodeStyles["default"]
    node_highlight = plan.nodeStyles["highlight"]
    edge_default = plan.edgeStyles["default"]
    edge_active = plan.edgeStyles["active"]

    return "\n".join(
        [
            "/* Aesthetic Intelligence Styles */",
            f"svg {{ background: {plan.background}; }}",
            f".ai-node-shape {{ fill: {node_default.fill} !important; stroke: {node_default.stroke} !important; stroke-width: {node_default.strokeWidth}px !important; }}",
            f".ai-node-highlight {{ fill: {node_highlight.fill} !important; stroke: {node_highlight.stroke} !important; stroke-width: {node_highlight.strokeWidth}px !important; }}",
            f".ai-node-text {{ fill: {text_color} !important; font-family: {plan.font.family}; font-weight: {plan.font.weight}; }}",
            f".ai-edge-line {{ stroke: {edge_default.stroke} !important; stroke-width: {edge_default.strokeWidth}px !important; }}",
            f".ai-edge-active {{ stroke: {edge_active.stroke} !important; stroke-width: {edge_active.strokeWidth}px !important; }}",
        ]
    )


def apply_aesthetic_plan(
    svg_text: str,
    plan: AestheticPlan,
    graph: Optional[SVGStructuralGraph] = None,
    highlight_override: Optional[HighlightSelection] = None,
) -> str:
    root = ET.fromstring(svg_text)
    graph = graph or analyze_svg(svg_text, "svg-aesthetic")
    highlight = highlight_override or _select_highlights(graph)

    id_index: Dict[str, ET.Element] = {}
    for el in root.iter():
        el_id = el.get("id")
        if el_id:
            id_index[el_id] = el

    for node in graph.nodes:
        el = id_index.get(node.id)
        if not el:
            continue
        el.set("data-kind", "node")
        _ensure_class(el, "ai-node")
        shape = _find_first_shape(el)
        if shape is not None:
            _ensure_class(shape, "ai-node-shape")
            if node.id in highlight.node_ids:
                _ensure_class(shape, "ai-node-highlight")
                shape.set("fill", plan.nodeStyles["highlight"].fill)
                shape.set("stroke", plan.nodeStyles["highlight"].stroke)
                shape.set("stroke-width", str(plan.nodeStyles["highlight"].strokeWidth))
                _set_style_attr(shape, {
                    "fill": plan.nodeStyles["highlight"].fill,
                    "stroke": plan.nodeStyles["highlight"].stroke,
                    "stroke-width": str(plan.nodeStyles["highlight"].strokeWidth),
                })
            else:
                shape.set("fill", plan.nodeStyles["default"].fill)
                shape.set("stroke", plan.nodeStyles["default"].stroke)
                shape.set("stroke-width", str(plan.nodeStyles["default"].strokeWidth))
                _set_style_attr(shape, {
                    "fill": plan.nodeStyles["default"].fill,
                    "stroke": plan.nodeStyles["default"].stroke,
                    "stroke-width": str(plan.nodeStyles["default"].strokeWidth),
                })
        for text_el in _find_text_elements(el):
            _ensure_class(text_el, "ai-node-text")
            text_el.set("font-family", plan.font.family)
            text_el.set("font-weight", plan.font.weight)
            _set_style_attr(text_el, {
                "fill": "#0f172a" if _get_luminance(plan.background) > 0.6 else "#f8fafc",
                "font-family": plan.font.family,
                "font-weight": plan.font.weight,
            })

    for edge in graph.edges:
        el = id_index.get(edge.id)
        if not el:
            continue
        el.set("data-kind", "edge")
        _ensure_class(el, "ai-edge")
        edge_shape = None
        if _strip_ns(el.tag) in EDGE_TAGS:
            edge_shape = el
        else:
            for child in el.iter():
                if _strip_ns(child.tag) in EDGE_TAGS:
                    edge_shape = child
                    break
        if edge_shape is None:
            continue
        _ensure_class(edge_shape, "ai-edge-line")
        if edge.id in highlight.edge_ids:
            _ensure_class(edge_shape, "ai-edge-active")
            edge_shape.set("stroke", plan.edgeStyles["active"].stroke)
            edge_shape.set("stroke-width", str(plan.edgeStyles["active"].strokeWidth))
            _set_style_attr(edge_shape, {
                "stroke": plan.edgeStyles["active"].stroke,
                "stroke-width": str(plan.edgeStyles["active"].strokeWidth),
            })
        else:
            edge_shape.set("stroke", plan.edgeStyles["default"].stroke)
            edge_shape.set("stroke-width", str(plan.edgeStyles["default"].strokeWidth))
            _set_style_attr(edge_shape, {
                "stroke": plan.edgeStyles["default"].stroke,
                "stroke-width": str(plan.edgeStyles["default"].strokeWidth),
            })

    style_el = None
    for child in root:
        if _strip_ns(child.tag) == "style" and child.get("id") == "ai-aesthetic-style":
            style_el = child
            break
    if style_el is None:
        style_el = ET.Element("style", {"id": "ai-aesthetic-style"})
    else:
        root.remove(style_el)
    root.append(style_el)
    style_el.text = _build_css(plan)

    # Normalize namespaces so downstream consumers get a <svg> root without prefixes
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

    return ET.tostring(root, encoding="unicode")
