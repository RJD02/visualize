"""Translate StructuralIR to PlantUML."""
from __future__ import annotations

from typing import List
import hashlib

from src.ir.structural_ir import StructuralIR


def _safe_id(value: str) -> str:
    return ''.join(c if c.isalnum() else '_' for c in value)


def structural_ir_to_plantuml(ir: StructuralIR) -> str:
    ir = ir.normalized()
    direction = "left to right direction" if ir.layout == "left-to-right" else "top to bottom direction"

    if ir.diagram_kind == "sequence":
        parts: List[str] = ["@startuml", f"title {ir.title or 'Sequence Diagram'}"]
        for node in ir.nodes:
            parts.append(f'participant "{node.label or node.id}" as {_safe_id(node.id)}')
        edges = sorted(ir.edges, key=lambda e: e.order or 0)
        for edge in edges:
            label = f" : {edge.label}" if edge.label else ""
            parts.append(f"{_safe_id(edge.from_)} -> {_safe_id(edge.to)}{label}")
        parts.append("@enduml")
    else:
        parts = ["@startuml", direction, f"title {ir.title or 'Architecture Diagram'}"]
        for node in ir.nodes:
            parts.append(f'component "{node.label or node.id}" as {_safe_id(node.id)}')
        for edge in ir.edges:
            label = f" : {edge.label}" if edge.label else ""
            parts.append(f"{_safe_id(edge.from_)} --> {_safe_id(edge.to)}{label}")
        parts.append("@enduml")

    plantuml = "\n".join(parts)
    plantuml = plantuml + "\n' fingerprint: " + hashlib.sha256(plantuml.encode("utf-8")).hexdigest()[:8]
    return plantuml
