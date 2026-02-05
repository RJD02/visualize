from typing import List
from .semantic_ir import SemanticIR
import hashlib


def _safe_id(s: str) -> str:
    return ''.join(c if c.isalnum() else '_' for c in s)


def _sorted_components(ir: SemanticIR):
    return sorted(ir.components, key=lambda c: c.id)


def ir_to_plantuml(ir: SemanticIR, diagram_type: str = "context") -> str:
    """
    Deterministic PlantUML generation from SemanticIR.
    diagram_type: context|container|component|sequence (sequence partial)
    """
    parts: List[str] = ["@startuml", f"title {ir.title or 'Architecture Diagram'}"]
    # stable ordering for determinism
    for actor in sorted(ir.actors, key=lambda a: a.id):
        parts.append(f'actor "{actor.name}" as { _safe_id(actor.id) }')

    # Boundaries -> packages
    for boundary in sorted(ir.boundaries, key=lambda b: b.id):
        parts.append(f'package "{boundary.name}" as { _safe_id(boundary.id) } {{')
        for child_id in sorted(boundary.children):
            comp = next((c for c in ir.components if c.id == child_id), None)
            if comp:
                parts.append(f'  component "{comp.name}" as { _safe_id(comp.id) }')
        parts.append('}')

    # components not in boundaries
    boundary_children = {c for b in ir.boundaries for c in b.children}
    for comp in _sorted_components(ir):
        if comp.id in boundary_children:
            continue
        parts.append(f'component "{comp.name}" as { _safe_id(comp.id) }')

    # relationships deterministic (sort by source,target,label)
    rels = sorted(ir.relationships, key=lambda r: (r.source, r.target, r.label or ""))
    for r in rels:
        src = _safe_id(r.source)
        tgt = _safe_id(r.target)
        arrow = "--" if r.type == "association" else "->"
        if r.direction == "<-":
            arrow = "<-"
        label = f' : {r.label}' if r.label else ""
        parts.append(f'{src} {arrow} {tgt}{label}')

    # minimal sequence support: relationships with order produce sequence notes (future)
    if diagram_type == "sequence":
        parts = ["@startuml", f"title {ir.title or 'Sequence Diagram'}"]
        participants = { _safe_id(c.id): c for c in ir.components }
        for pid in sorted(participants):
            parts.append(f'participant "{participants[pid].name}" as {pid}')
        msgs = [r for r in ir.relationships if r.order is not None]
        msgs = sorted(msgs, key=lambda m: m.order)
        for m in msgs:
            parts.append(f'{_safe_id(m.source)} -> {_safe_id(m.target)} : {m.label or ""}')
    parts.append("@enduml")
    plant = "\n".join(parts)
    # stable fingerprint for debugging
    plant = plant + "\n' fingerprint: " + hashlib.sha256(plant.encode("utf-8")).hexdigest()[:8]
    return plant
