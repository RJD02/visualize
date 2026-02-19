from __future__ import annotations

from typing import List
from src.ir.semantic_ir import SemanticIR, Component, SystemBoundary, Relationship


def _safe_id(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name).lower()


def plan_to_semantic_ir(plan, diagram_type: str = "context", prompt: str = None) -> SemanticIR:
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

    # Deterministic relationship extraction from prompt (if provided)
    if prompt:
        try:
            from src.ir.relationship_extractor import extract_relationships
            block_ids = [c.id for c in components]
            blocks = [{"id": bid} for bid in block_ids]
            edges = extract_relationships(prompt, blocks)
            for edge in edges:
                # Only add if not already present
                if not any(r.source == edge.from_ and r.target == edge.to for r in rels):
                    rels.append(Relationship(source=edge.from_, target=edge.to, type=edge.relation_type, label=edge.label, order=None))
        except Exception as e:
            pass  # fail open, don't block IR

    ir = SemanticIR(id=_safe_id(title), title=title, actors=[], components=components, relationships=rels, boundaries=boundaries)

    # Apply semantic clustering before layout/rendering (specs_v45)
    try:
        from src.ir.semantic_clustering import cluster_ir
        ir = cluster_ir(ir)
    except Exception:
        # fail-open: do not block IR generation on clustering errors
        pass

    return ir
