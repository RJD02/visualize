"""Deterministic SVG-as-IR generator and renderer."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import xml.etree.ElementTree as ET

from src.models.architecture_plan import ArchitecturePlan
from src.tools.ir_validator import validate_svg_ir
from src.utils.config import settings
from src.utils.file_utils import ensure_dir


@dataclass(frozen=True)
class IRNode:
    node_id: str
    label: str
    role: str
    zone: str


@dataclass(frozen=True)
class IREdge:
    edge_id: str
    from_id: str
    to_id: str
    rel_type: str


@dataclass
class IRModel:
    diagram_type: str
    layout: str
    zone_order: List[str]
    nodes: List[IRNode]
    edges: List[IREdge]


ZONE_TITLES = {
    "clients": "clients",
    "edge": "edge",
    "core_services": "core_services",
    "external_services": "external_services",
    "data_stores": "data_stores",
}

ROLE_BY_ZONE = {
    "clients": "client",
    "edge": "gateway",
    "core_services": "service",
    "external_services": "external",
    "data_stores": "db",
}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "item"


def build_ir_from_plan(plan: ArchitecturePlan, diagram_type: str, overrides: Optional[Dict[str, object]] = None) -> IRModel:
    overrides = overrides or {}
    layout = overrides.get("layout") or plan.visual_hints.layout
    if diagram_type in {"sequence", "runtime"}:
        layout = "left-to-right"
    zone_order = overrides.get("zone_order") or list(ZONE_TITLES.keys())

    filtered = _filter_nodes_by_diagram(plan, diagram_type, zone_order)
    nodes: List[IRNode] = []
    for zone, items in filtered.items():
        for item in items:
            node_id = f"node_{_slug(item)}"
            nodes.append(IRNode(node_id=node_id, label=item, role=ROLE_BY_ZONE.get(zone, "service"), zone=zone))

    # Map node labels to IDs for pattern matching and expansion
    node_label_to_id = {node.label: node.node_id for node in nodes}
    edges: List[IREdge] = []
    seen = set()

    def _match_labels(pattern: str) -> List[str]:
        # Support simple glob '*' matching (e.g. 'packages/*') against node labels
        if "*" in pattern:
            regex = "^" + re.escape(pattern).replace("\\*", ".*") + "$"
            r = re.compile(regex, re.IGNORECASE)
            return [n.label for n in nodes if r.match(n.label)]
        # Exact match
        return [pattern] if pattern in node_label_to_id else []

    for rel in plan.relationships:
        from_labels = _match_labels(rel.from_)
        to_labels = _match_labels(rel.to)
        for f_label in from_labels:
            for t_label in to_labels:
                from_id = node_label_to_id.get(f_label)
                to_id = node_label_to_id.get(t_label)
                if not from_id or not to_id:
                    continue
                key = (from_id, to_id, rel.type)
                if key in seen:
                    continue
                seen.add(key)
                edge_id = f"edge_{_slug(f_label)}_{_slug(t_label)}_{_slug(rel.type)}"
                edges.append(IREdge(edge_id=edge_id, from_id=from_id, to_id=to_id, rel_type=rel.type))

    return IRModel(
        diagram_type=diagram_type,
        layout=layout,
        zone_order=list(zone_order),
        nodes=nodes,
        edges=edges,
    )


def _filter_nodes_by_diagram(plan: ArchitecturePlan, diagram_type: str, zone_order: List[str]) -> Dict[str, List[str]]:
    zones = {
        "clients": list(plan.zones.clients),
        "edge": list(plan.zones.edge),
        "core_services": list(plan.zones.core_services),
        "external_services": list(plan.zones.external_services),
        "data_stores": list(plan.zones.data_stores),
    }

    if diagram_type == "system_context":
        # High-level: pick first item from each populated zone
        return {zone: (items[:1] if items else []) for zone, items in zones.items() if zone in zone_order}

    if diagram_type == "container":
        # Mid-level: keep edge, core services, data stores
        return {
            "edge": zones.get("edge", []),
            "core_services": zones.get("core_services", []),
            "data_stores": zones.get("data_stores", []),
        }

    if diagram_type == "component":
        # Detailed: focus on core services only
        return {
            "core_services": zones.get("core_services", []),
        }

    if diagram_type == "sequence":
        # Sequence view: prioritize clients/edge/core
        return {
            "clients": zones.get("clients", []),
            "edge": zones.get("edge", []),
            "core_services": zones.get("core_services", []),
        }

    return {zone: items for zone, items in zones.items() if zone in zone_order}


def _layout_nodes(ir: IRModel) -> Dict[str, Dict[str, float]]:
    positions: Dict[str, Dict[str, float]] = {}
    x_base = 40
    y_base = 60
    zone_gap = 120
    item_gap = 80

    zone_offsets: Dict[str, float] = {}
    for idx, zone in enumerate(ir.zone_order):
        if ir.layout == "left-to-right":
            zone_offsets[zone] = x_base + idx * zone_gap
        else:
            zone_offsets[zone] = y_base + idx * zone_gap

    zone_counts: Dict[str, int] = {zone: 0 for zone in ir.zone_order}
    for node in ir.nodes:
        count = zone_counts.get(node.zone, 0)
        if ir.layout == "left-to-right":
            x = zone_offsets.get(node.zone, x_base)
            y = y_base + count * item_gap
        else:
            x = x_base + count * item_gap
            y = zone_offsets.get(node.zone, y_base)
        positions[node.node_id] = {"x": x, "y": y}
        zone_counts[node.zone] = count + 1

    return positions


def _neutral_stroke() -> str:
    return "#0f172a"


def ir_to_svg(ir: IRModel) -> str:
    positions = _layout_nodes(ir)
    node_h = 48
    padding_bottom = 60
    width = 960
    # compute needed height based on node positions so tall diagrams aren't clipped
    max_y = 0
    for pos in positions.values():
        y = pos.get("y", 0)
        max_y = max(max_y, y + node_h)
    height = max(720, int(max_y + padding_bottom))

    svg = ET.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg",
        "width": str(width),
        "height": str(height),
        "viewBox": f"0 0 {width} {height}",
        "data-diagram-type": ir.diagram_type,
    })

    background_group = ET.SubElement(svg, "g", {
        "id": "bg_group",
        "data-kind": "background",
        "data-role": "background",
    })
    ET.SubElement(background_group, "rect", {
        "id": "bg",
        "x": "0",
        "y": "0",
        "width": str(width),
        "height": str(height),
        "fill": "#f8fafc",
    })

    title_group = ET.SubElement(svg, "g", {
        "id": "label_title",
        "data-kind": "label",
        "data-role": "title",
    })
    title_text = ET.SubElement(title_group, "text", {
        "id": "label_title_text",
        "class": "zone-text",
        "x": "24",
        "y": "24",
    })
    title_text.text = _diagram_title(ir.diagram_type)

    metadata = ET.SubElement(svg, "metadata", {"id": "ir_metadata"})
    metadata.text = json.dumps({
        "diagram_type": ir.diagram_type,
        "layout": ir.layout,
        "zone_order": ir.zone_order,
        "nodes": [node.__dict__ for node in ir.nodes],
        "edges": [edge.__dict__ for edge in ir.edges],
    })

    zone_groups: Dict[str, ET.Element] = {}
    for idx, zone in enumerate(ir.zone_order):
        group = ET.SubElement(svg, "g", {
            "id": f"boundary_{zone}",
            "data-kind": "boundary",
            "data-role": zone,
        })
        zone_groups[zone] = group
        if ir.layout == "left-to-right":
            x = 20 + idx * 120
            y = 40
            w = 140
            h = max(140, height - 80)
        else:
            x = 20
            y = 40 + idx * 120
            w = width - 40
            h = 140
        rect = ET.SubElement(group, "rect", {
            "id": f"boundary_{zone}_rect",
            "class": "zone-rect",
            "x": str(x),
            "y": str(y),
            "width": str(w),
            "height": str(h),
        })
        rect.set("fill", "none")
        rect.set("stroke", _neutral_stroke())
        label = ET.SubElement(group, "text", {
            "id": f"boundary_{zone}_label",
            "class": "zone-text",
            "x": str(x + 6),
            "y": str(y + 16),
        })
        label.text = ZONE_TITLES.get(zone, zone)

    for node in ir.nodes:
        pos = positions[node.node_id]
        group = ET.SubElement(svg, "g", {
            "id": node.node_id,
            "data-kind": "node",
            "data-role": node.role,
            "data-block-id": node.node_id,
        })
        rect = ET.SubElement(group, "rect", {
            "id": f"{node.node_id}_rect",
            "class": "node-rect",
            "x": str(pos["x"]),
            "y": str(pos["y"]),
            "width": "140",
            "height": "48",
        })
        rect.set("fill", "none")
        rect.set("stroke", _neutral_stroke())
        text = ET.SubElement(group, "text", {
            "id": f"{node.node_id}_text",
            "class": "node-text",
            "x": str(pos["x"] + 8),
            "y": str(pos["y"] + 28),
        })
        text.text = node.label

    for edge in ir.edges:
        if edge.from_id not in positions or edge.to_id not in positions:
            continue
        start = positions[edge.from_id]
        end = positions[edge.to_id]
        group = ET.SubElement(svg, "g", {
            "id": edge.edge_id,
            "data-kind": "edge",
            "data-role": edge.rel_type,
        })
        line = ET.SubElement(group, "line", {
            "id": f"{edge.edge_id}_line",
            "class": "edge-line",
            "x1": str(start["x"] + 140),
            "y1": str(start["y"] + 24),
            "x2": str(end["x"]),
            "y2": str(end["y"] + 24),
        })
        line.set("stroke", _neutral_stroke())

    svg_text = ET.tostring(svg, encoding="unicode")
    validate_svg_ir(svg_text)
    return svg_text


def render_ir_svg(svg_text: str, output_name: str) -> str:
    output_dir = ensure_dir(settings.output_dir)
    output_path = Path(output_dir) / f"{output_name}.svg"
    output_path.write_text(svg_text, encoding="utf-8")
    return str(output_path)


def generate_svg_from_plan(plan: ArchitecturePlan, diagram_type: str, output_name: str, overrides: Optional[Dict[str, object]] = None) -> Dict[str, str]:
    ir = build_ir_from_plan(plan, diagram_type, overrides=overrides)
    svg_text = ir_to_svg(ir)
    svg_file = render_ir_svg(svg_text, output_name)
    return {"svg": svg_text, "svg_file": svg_file}


def edit_ir_svg(svg_text: str, instruction: str) -> str:
    if not svg_text or not svg_text.strip():
        # create a minimal SVG with metadata to allow edits when original IR is empty
        payload = {
            "diagram_type": "diagram",
            "layout": "top-down",
            "zone_order": list(ZONE_TITLES.keys()),
            "nodes": [],
            "edges": [],
        }
        svg = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "width": "800", "height": "600"})
        meta = ET.SubElement(svg, "metadata", {"id": "ir_metadata"})
        meta.text = json.dumps(payload)
        root = svg
    else:
        try:
            root = ET.fromstring(svg_text)
        except ET.ParseError as exc:
            raise ValueError(f"Invalid SVG XML: {exc}") from exc

    metadata = None
    for elem in root.iter():
        if elem.tag.endswith("metadata"):
            metadata = elem
            break
    if metadata is None or not metadata.text:
        raise ValueError("Missing IR metadata.")

    payload = json.loads(metadata.text)
    zone_order = payload.get("zone_order", [])
    layout = payload.get("layout")

    text = (instruction or "").lower()
    move_above = re.search(r"move\s+(.+?)\s+above\s+(.+)", text)
    move_below = re.search(r"move\s+(.+?)\s+below\s+(.+)", text)

    def _match_zone(fragment: str) -> Optional[str]:
        for zone in zone_order:
            if zone.replace("_", " ") in fragment or zone in fragment:
                return zone
        return None

    if move_above:
        first = _match_zone(move_above.group(1))
        second = _match_zone(move_above.group(2))
        if first and second:
            zone_order = [z for z in zone_order if z not in {first, second}]
            idx = 0
            zone_order.insert(idx, first)
            zone_order.insert(idx + 1, second)
    elif move_below:
        first = _match_zone(move_below.group(1))
        second = _match_zone(move_below.group(2))
        if first and second:
            zone_order = [z for z in zone_order if z not in {first, second}]
            idx = 0
            zone_order.insert(idx, second)
            zone_order.insert(idx + 1, first)

    def _coerce_node(raw: dict) -> IRNode:
        data = dict(raw or {})
        if "node_id" not in data and "id" in data:
            data["node_id"] = data.get("id")
        allowed = {"node_id", "label", "role", "zone"}
        cleaned = {k: v for k, v in data.items() if k in allowed}
        return IRNode(**cleaned)

    def _coerce_edge(raw: dict) -> IREdge:
        data = dict(raw or {})
        if "from_id" not in data and "from" in data:
            data["from_id"] = data.get("from")
        if "to_id" not in data and "to" in data:
            data["to_id"] = data.get("to")
        allowed = {"edge_id", "from_id", "to_id", "rel_type"}
        cleaned = {k: v for k, v in data.items() if k in allowed}
        return IREdge(**cleaned)

    ir = IRModel(
        diagram_type=payload.get("diagram_type", "diagram"),
        layout=layout or "top-down",
        zone_order=zone_order,
        nodes=[_coerce_node(node) for node in payload.get("nodes", [])],
        edges=[_coerce_edge(edge) for edge in payload.get("edges", [])],
    )
    return ir_to_svg(ir)


def _diagram_title(diagram_type: str) -> str:
    mapping = {
        "system_context": "C4 Context Diagram",
        "container": "C4 Container Diagram",
        "sequence": "Runtime Flow Diagram",
        "runtime": "Runtime Flow Diagram",
        "repo": "Repo Architecture Diagram",
        "repo_architecture": "Repo Architecture Diagram",
    }
    return mapping.get(diagram_type, "System Architecture Diagram")
