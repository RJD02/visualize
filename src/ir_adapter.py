"""Adapters between IR v2 and SVG outputs."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple
from xml.etree import ElementTree as ET


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _center(bbox: Dict[str, Any]) -> Tuple[float, float]:
    return (
        float(bbox.get("x", 0)) + float(bbox.get("w", 0)) / 2,
        float(bbox.get("y", 0)) + float(bbox.get("h", 0)) / 2,
    )


def render_v2_svg(wrapper: Dict[str, Any]) -> str:
    ir = wrapper.get("ir", {})
    diagram = ir.get("diagram", {})
    blocks = diagram.get("blocks", []) or []
    relations = diagram.get("relations", []) or []

    max_x = 0.0
    max_y = 0.0
    for block in blocks:
        bbox = block.get("bbox", {})
        max_x = max(max_x, float(bbox.get("x", 0)) + float(bbox.get("w", 0)))
        max_y = max(max_y, float(bbox.get("y", 0)) + float(bbox.get("h", 0)))

    width = int(max(800, max_x + 60))
    height = int(max(600, max_y + 60))

    svg = ET.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg",
        "width": str(width),
        "height": str(height),
        "viewBox": f"0 0 {width} {height}",
        "data-diagram-id": str(wrapper.get("diagram_id", "diagram")),
    })

    meta = ET.SubElement(svg, "metadata", {"id": "ir_metadata"})
    meta.text = json.dumps(wrapper)

    for block in blocks:
        if block.get("hidden"):
            continue
        bbox = block.get("bbox") or {}
        x = str(bbox.get("x", 0))
        y = str(bbox.get("y", 0))
        w = str(bbox.get("w", 140))
        h = str(bbox.get("h", 48))
        block_id = str(block.get("id"))
        group = ET.SubElement(svg, "g", {
            "id": block_id,
            "data-kind": "node",
            "data-block-id": block_id,
            "data-type": str(block.get("type", "component")),
        })
        rect = ET.SubElement(group, "rect", {
            "id": f"{block_id}_rect",
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "rx": "6",
            "class": "node-rect",
        })
        style = block.get("style") or {}
        if style.get("color"):
            rect.set("fill", style.get("color"))
        else:
            rect.set("fill", "none")
        if style.get("stroke"):
            rect.set("stroke", style.get("stroke"))
        text = ET.SubElement(group, "text", {
            "id": f"{block_id}_text",
            "x": str(float(bbox.get("x", 0)) + 8),
            "y": str(float(bbox.get("y", 0)) + 24),
            "class": "node-text",
        })
        text.text = str(block.get("text") or "")

    for rel in relations:
        src_id = rel.get("from")
        tgt_id = rel.get("to")
        src = next((b for b in blocks if b.get("id") == src_id), None)
        tgt = next((b for b in blocks if b.get("id") == tgt_id), None)
        if not src or not tgt:
            continue
        start = _center(src.get("bbox", {}))
        end = _center(tgt.get("bbox", {}))
        edge_id = rel.get("id") or f"edge_{src_id}_{tgt_id}"
        group = ET.SubElement(svg, "g", {
            "id": edge_id,
            "data-kind": "edge",
            "data-role": str(rel.get("type", "rel")),
        })
        line = ET.SubElement(group, "line", {
            "id": f"{edge_id}_line",
            "x1": str(start[0]),
            "y1": str(start[1]),
            "x2": str(end[0]),
            "y2": str(end[1]),
            "class": "edge-line",
        })
        line.set("stroke", "#0f172a")

    return ET.tostring(svg, encoding="unicode")


def v2_from_svg(svg_text: str, *, diagram_id: str) -> Dict[str, Any]:
    root = ET.fromstring(svg_text)
    metadata = None
    for elem in root.iter():
        if _strip_ns(elem.tag) == "metadata" and (elem.get("id") == "ir_metadata" or (elem.text and "diagram_type" in elem.text)):
            metadata = elem
            break

    node_zone: Dict[str, str] = {}
    node_label: Dict[str, str] = {}
    relations: List[Dict[str, Any]] = []
    if metadata is not None and metadata.text:
        try:
            meta_payload = json.loads(metadata.text)
            nodes = meta_payload.get("nodes") or meta_payload.get("ir", {}).get("diagram", {}).get("blocks") or []
            for node in nodes:
                node_id = node.get("node_id") or node.get("id")
                if node_id:
                    node_zone[node_id] = node.get("zone") or node.get("group") or "core_services"
                    if node.get("label"):
                        node_label[node_id] = node.get("label")
            edges = meta_payload.get("edges") or meta_payload.get("ir", {}).get("diagram", {}).get("relations") or []
            for edge in edges:
                rel_from = edge.get("from_id") or edge.get("from")
                rel_to = edge.get("to_id") or edge.get("to")
                if rel_from and rel_to:
                    relations.append({"from": rel_from, "to": rel_to, "label": edge.get("label") or edge.get("type")})
        except Exception:
            pass

    blocks: List[Dict[str, Any]] = []
    for group in root.iter():
        if _strip_ns(group.tag) != "g":
            continue
        if group.get("data-kind") != "node":
            continue
        block_id = group.get("data-block-id") or group.get("id")
        if not block_id:
            continue
        rect = None
        label_text = None
        for child in list(group):
            if _strip_ns(child.tag) == "rect" and rect is None:
                rect = child
            if _strip_ns(child.tag) == "text" and label_text is None:
                label_text = child.text
        bbox = {
            "x": float(rect.get("x", 0)) if rect is not None else 0.0,
            "y": float(rect.get("y", 0)) if rect is not None else 0.0,
            "w": float(rect.get("width", 140)) if rect is not None else 140.0,
            "h": float(rect.get("height", 48)) if rect is not None else 48.0,
        }
        text_value = label_text or node_label.get(block_id) or block_id
        block_type = group.get("data-type") or group.get("data-role") or "component"
        blocks.append({
            "id": block_id,
            "type": block_type,
            "text": text_value,
            "bbox": bbox,
            "style": {},
            "annotations": {},
            "zone": node_zone.get(block_id) or "core_services",
            "version": 1,
        })

    wrapper = {
        "diagram_id": diagram_id,
        "ir_version": 1,
        "parent_version": None,
        "ir": {
            "diagram": {
                "id": diagram_id,
                "type": "system_architecture",
                "blocks": blocks,
                "relations": relations,
            }
        },
    }
    return wrapper
