from __future__ import annotations

from typing import List
from src.ir.semantic_ir import SemanticIR, Component, SystemBoundary, Relationship


def _safe_id(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name).lower()


def plan_to_semantic_ir(plan, diagram_type: str = "context") -> SemanticIR:
    title = getattr(plan, "system_name", "Architecture")
    components = []
    boundaries = []
    seen = set()

    # zones -> boundaries and components
    zones = getattr(plan, "zones", None)
    if zones:
        for zone_name, members in zones.model_dump().items():
            if not members:
                continue
            boundary_id = _safe_id(zone_name)
            children = []
            for m in members:
                cid = _safe_id(m)
                if cid not in seen:
                    components.append(Component(id=cid, name=m))
                    seen.add(cid)
                children.append(cid)
            boundaries.append(SystemBoundary(id=boundary_id, name=zone_name, children=children))

    # relationships
    rels: List[Relationship] = []
    for idx, r in enumerate(getattr(plan, "relationships", []) or []):
        src = _safe_id(r.from_)
        tgt = _safe_id(r.to)
        # ensure components exist for endpoints
        for n, label in ((src, r.from_), (tgt, r.to)):
            if n not in seen:
                components.append(Component(id=n, name=label))
                seen.add(n)
        rels.append(Relationship(source=src, target=tgt, type="association", label=getattr(r, "description", None), order=None))

    ir = SemanticIR(id=_safe_id(title), title=title, actors=[], components=components, relationships=rels, boundaries=boundaries)
    return ir
