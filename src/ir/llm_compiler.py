from __future__ import annotations
from typing import Optional
from src.ir.semantic_ir import SemanticIR
from src.ir.uml_ast import UMLModel, UMLActor, UMLComponent, UMLPackage, UMLRelationship


def compile_ir_to_uml(ir: SemanticIR, diagram_type: str = "context") -> UMLModel:
    """Deterministic compiler pass from SemanticIR -> UMLModel.

    This function is deterministic and does not call external LLMs. It is
    designed to be a placeholder where a constrained LLM pass could be
    inserted; for now it performs a direct mapping.
    """
    model = UMLModel(id=ir.id, title=ir.title or "Architecture Diagram")
    # map actors
    for a in sorted(ir.actors, key=lambda x: x.id):
        model.actors.append(UMLActor(id=_safe(a.id), name=a.name))

    # components
    for c in sorted(ir.components, key=lambda x: x.id):
        model.components.append(UMLComponent(id=_safe(c.id), name=c.name, stereotype=c.type))

    # packages from boundaries
    for b in sorted(ir.boundaries, key=lambda x: x.id):
        model.packages.append(UMLPackage(id=_safe(b.id), name=b.name, children=[_safe(ch) for ch in b.children]))

    # relationships
    for r in sorted(ir.relationships, key=lambda x: (x.source, x.target, x.label or "")):
        arrow = "--" if r.type == "association" else "->"
        if r.direction == "<-":
            arrow = "<-"
        model.relationships.append(UMLRelationship(source=_safe(r.source), target=_safe(r.target), arrow=arrow, label=r.label))

    return model


def _safe(s: str) -> str:
    return ''.join(c if c.isalnum() else '_' for c in s)
