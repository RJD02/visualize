"""Translate RendererIR into renderer-specific inputs."""
from __future__ import annotations

from typing import Dict, List

from src.renderers.renderer_ir import RendererIR


def _sanitize_id(value: str) -> str:
    if not value:
        return "node"
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value.strip())
    if not cleaned[0].isalpha():
        cleaned = f"n_{cleaned}"
    return cleaned


def _node_label(node_id: str, label: str | None) -> str:
    return label or node_id


def ir_to_mermaid(ir: RendererIR) -> str:
    ir = ir.normalized()
    direction = "LR" if ir.layout == "left-to-right" else "TB"
    lines: List[str] = [f"flowchart {direction}"]
    id_map: Dict[str, str] = {}
    for node in ir.nodes:
        safe_id = _sanitize_id(node.id)
        suffix = 1
        while safe_id in id_map.values():
            suffix += 1
            safe_id = f"{safe_id}_{suffix}"
        id_map[node.id] = safe_id

    groups = {g.id: g for g in ir.groups}
    grouped_nodes = set()
    for group in ir.groups:
        label = group.label or group.id
        lines.append(f"subgraph {group.id}[\"{label}\"]")
        for member in group.members:
            node = next((n for n in ir.nodes if n.id == member), None)
            if not node:
                continue
            grouped_nodes.add(node.id)
            node_label = _node_label(node.id, node.label)
            lines.append(f"  {id_map[node.id]}[\"{node_label}\"]")
        lines.append("end")

    for node in ir.nodes:
        if node.id in grouped_nodes:
            continue
        node_label = _node_label(node.id, node.label)
        lines.append(f"{id_map[node.id]}[\"{node_label}\"]")

    for edge in ir.edges:
        source = id_map.get(edge.from_, _sanitize_id(edge.from_))
        target = id_map.get(edge.to, _sanitize_id(edge.to))
        label = f"|{edge.label}|" if edge.label else ""
        lines.append(f"{source} -->{label} {target}")

    return "\n".join(lines)


def ir_to_plantuml(ir: RendererIR) -> str:
    ir = ir.normalized()
    direction = "left to right direction" if ir.layout == "left-to-right" else "top to bottom direction"
    lines: List[str] = ["@startuml", direction]
    for node in ir.nodes:
        label = _node_label(node.id, node.label)
        alias = _sanitize_id(node.id)
        lines.append(f"component \"{label}\" as {alias}")
    for edge in ir.edges:
        source = _sanitize_id(edge.from_)
        target = _sanitize_id(edge.to)
        label = f" : {edge.label}" if edge.label else ""
        lines.append(f"{source} --> {target}{label}")
    lines.append("@enduml")
    return "\n".join(lines)


def _structurizr_element_kind(kind: str) -> str:
    lowered = (kind or "").lower()
    if lowered in {"person", "user", "actor"}:
        return "person"
    if lowered in {"system", "software_system", "software system"}:
        return "softwareSystem"
    if lowered in {"component", "module"}:
        return "component"
    if lowered in {"database", "datastore", "db"}:
        return "container"
    if lowered in {"container", "service", "api"}:
        return "container"
    return "container"


def ir_to_structurizr_dsl(ir: RendererIR) -> str:
    import json

    ir = ir.normalized()
    title = ir.title or "Generated Workspace"
    direction = "LeftRight" if ir.layout == "left-to-right" else "TopBottom"

    people = []
    systems = []
    id_map: Dict[str, str] = {}
    next_id = 1

    for node in ir.nodes:
        node_id = str(next_id)
        next_id += 1
        id_map[node.id] = node_id
        kind = _structurizr_element_kind(node.kind)
        label = _node_label(node.id, node.label)
        if kind == "person":
            people.append({"id": node_id, "name": label})
        else:
            systems.append({"id": node_id, "name": label})

    if not systems:
        systems.append({"id": str(next_id), "name": "System"})
        system_id = str(next_id)
        next_id += 1
    else:
        system_id = systems[0]["id"]

    relationships = []
    for edge in ir.edges:
        src = id_map.get(edge.from_)
        tgt = id_map.get(edge.to)
        if not src or not tgt:
            continue
        rel_id = str(next_id)
        next_id += 1
        relationships.append({
            "id": rel_id,
            "sourceId": src,
            "destinationId": tgt,
            "description": edge.label or edge.type or "interaction",
        })

    elements = [{"id": p["id"]} for p in people] + [{"id": s["id"]} for s in systems]

    workspace = {
        "name": title,
        "description": "Generated",
        "model": {
            "people": people,
            "softwareSystems": systems,
            "relationships": relationships,
        },
        "views": {
            "systemContextViews": [
                {
                    "key": "SystemContext",
                    "softwareSystemId": system_id,
                    "description": "Generated",
                    "elements": elements,
                    "automaticLayout": {"rankDirection": direction},
                }
            ]
        },
    }
    return json.dumps(workspace, indent=2, sort_keys=True)
