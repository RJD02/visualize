"""Renderer router: choose renderer based on structural IR."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple as Tup, Any

from src.ir.schemas import StructuralIR as StructuralSchema
from src.translation.translators import (
    structural_to_mermaid,
    structural_to_structurizr,
    structural_to_plantuml,
)
from src.renderers.renderer_ir import RendererIR


@dataclass(frozen=True)
class RendererChoice:
    renderer: str
    reason: str


def _normalize_structural_ir(ir: StructuralSchema | RendererIR | dict | Any) -> StructuralSchema:
    if isinstance(ir, StructuralSchema):
        return ir

    nodes = []
    for n in getattr(ir, "nodes", []) or []:
        if isinstance(n, dict):
            normalized = dict(n)
            normalized.setdefault("id", normalized.get("ID"))
            normalized.setdefault("label", normalized.get("name") or normalized.get("id"))
            node_kind = normalized.get("kind") or normalized.get("type") or "Component"
            normalized.setdefault("kind", node_kind)
            normalized.setdefault("type", node_kind)
            nodes.append(normalized)
        else:
            nodes.append({
                "id": getattr(n, "id", None) or getattr(n, "ID", None),
                "label": getattr(n, "label", None) or getattr(n, "name", None) or getattr(n, "id", None),
                "type": getattr(n, "type", None) or getattr(n, "kind", None) or "Component",
                "kind": getattr(n, "kind", None) or getattr(n, "type", None),
            })

    edges = []
    for e in getattr(ir, "edges", []) or []:
        if isinstance(e, dict):
            normalized = dict(e)
            normalized.setdefault("source", normalized.get("from") or normalized.get("from_"))
            normalized.setdefault("target", normalized.get("to") or normalized.get("to_id"))
            normalized.setdefault("type", normalized.get("type") or normalized.get("label"))
            edges.append(normalized)
        else:
            src = getattr(e, "from_", None) or getattr(e, "from", None) or getattr(e, "source", None)
            tgt = getattr(e, "to", None) or getattr(e, "to_id", None) or getattr(e, "target", None)
            edges.append({
                "source": src,
                "target": tgt,
                "label": getattr(e, "label", None),
                "type": getattr(e, "type", None) or getattr(e, "rel_type", None) or getattr(e, "label", None),
            })

    struct = StructuralSchema(nodes=nodes, edges=edges)
    struct.diagram_kind = getattr(ir, "diagram_kind", getattr(struct, "diagram_kind", "")) or ""
    return struct


def _determine_renderer(
    ir: StructuralSchema | RendererIR | dict | Any,
    struct: StructuralSchema,
    override: Optional[str] = None,
) -> RendererChoice:
    if override:
        return RendererChoice(renderer=override, reason="override")

    diag_kind = getattr(ir, "diagram_kind", "") or getattr(struct, "diagram_kind", "")
    sequence_aliases = {"sequence", "flow", "runtime"}
    if diag_kind and diag_kind.lower() in sequence_aliases:
        return RendererChoice(renderer="mermaid", reason="explicit sequence diagram")

    node_kinds = []
    for n in (struct.nodes or []):
        if isinstance(n, dict):
            node_kinds.append((n.get("kind") or n.get("type") or ""))
        else:
            node_kinds.append(getattr(n, "kind", None) or getattr(n, "type", None))

    edge_types = []
    for e in (struct.edges or []):
        if isinstance(e, dict):
            edge_types.append(e.get("type") or e.get("label"))
        else:
            edge_types.append(getattr(e, "type", None) or getattr(e, "label", None))
    looks_like_participants = any(k and k.lower() in {"participant", "actor", "person"} for k in node_kinds)
    looks_like_message_edges = any(t and str(t).lower() in {"message", "interaction", "call"} for t in edge_types)

    participant_count = sum(1 for k in node_kinds if k and k.lower() in {"participant", "actor", "person"})
    if participant_count >= 2 and looks_like_message_edges:
        return RendererChoice(renderer="mermaid", reason="explicit sequence/participant IR")

    return RendererChoice(renderer="structurizr", reason="default architecture renderer")


def choose_renderer(ir: StructuralSchema | RendererIR | dict | Any, override: Optional[str] = None) -> RendererChoice:
    struct = _normalize_structural_ir(ir)
    return _determine_renderer(ir, struct, override)


def render_ir(ir: StructuralSchema | RendererIR | dict | Any, override: Optional[str] = None) -> Tup[str, RendererChoice]:
    """Render structural IR using translators and real renderers.

    Returns (svg_text, RendererChoice)
    """
    struct = _normalize_structural_ir(ir)
    choice = _determine_renderer(ir, struct, override)
    renderer = choice.renderer
    reason = choice.reason

    # Translate and render
    if renderer == "mermaid":
        inp = structural_to_mermaid(struct)
        # lazy import to avoid heavy deps at module import time
        from src.renderers.mermaid_renderer import render_mermaid_svg as _render_mermaid_svg

        svg = _render_mermaid_svg(inp)
    elif renderer == "structurizr":
        # prefer a conversion pipeline that yields SVG: StructuralIR -> PlantUML -> SVG
        from src.renderers.structurizr_renderer import render_structurizr_svg_from_structural

        svg = render_structurizr_svg_from_structural(struct)
    else:
        inp = structural_to_plantuml(struct)
        from src.renderers.plantuml_renderer import render_plantuml_svg_text as _render_plantuml_svg_text

        svg = _render_plantuml_svg_text(inp, output_name="renderer_plantuml")

    return svg, RendererChoice(renderer=renderer, reason=reason)
