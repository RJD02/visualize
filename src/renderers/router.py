"""Renderer router: choose renderer based on intent."""
from __future__ import annotations

from typing import Tuple


def choose_renderer(intent: str) -> Tuple[str, str]:
    """Return (renderer_name, justification).

    Renderers: mermaid, structurizr, plantuml
    """
    if intent in ("story", "sequence"):
        return "mermaid", "story/sequence -> mermaid"
    if intent in ("system_context", "container", "component"):
        return "structurizr", "architecture intents -> structurizr"
    return "plantuml", "fallback -> plantuml"


from dataclasses import dataclass
from typing import Optional, Tuple as Tup

from src.ir.schemas import StructuralIR as StructuralSchema
from src.translation.translators import (
    structural_to_mermaid,
    structural_to_structurizr,
    structural_to_plantuml,
)
from src.renderers import fake_renderers


@dataclass(frozen=True)
class RendererChoice:
    renderer: str
    reason: str


def render_ir(ir: StructuralIR, override: Optional[str] = None) -> Tup[str, RendererChoice]:
    """Render structural IR using translators and fake renderers (POC).

    Returns (svg_text, RendererChoice)
    """
    # Normalize IR to dict-based StructuralIR (dataclass) for translators
    if isinstance(ir, StructuralSchema):
        struct = ir
    else:
        nodes = []
        for n in getattr(ir, "nodes", []) or []:
            if isinstance(n, dict):
                nodes.append(n)
            else:
                nodes.append({
                    "id": getattr(n, "id", None) or getattr(n, "ID", None),
                    "label": getattr(n, "label", None) or getattr(n, "name", None) or getattr(n, "id", None),
                    "type": getattr(n, "type", None) or getattr(n, "kind", None) or "Component",
                })

        edges = []
        for e in getattr(ir, "edges", []) or []:
            if isinstance(e, dict):
                edges.append(e)
            else:
                src = getattr(e, "from_", None) or getattr(e, "from", None) or getattr(e, "source", None)
                tgt = getattr(e, "to", None) or getattr(e, "to_id", None) or getattr(e, "target", None)
                edges.append({"source": src, "target": tgt, "label": getattr(e, "label", None)})

        struct = StructuralSchema(nodes=nodes, edges=edges)

    # Decide renderer
    if override:
        renderer = override
        reason = "override"
    else:
        # Force mermaid for explicit sequence IRs
        if getattr(ir, "diagram_kind", "") == "sequence" or getattr(struct, "diagram_kind", "") == "sequence":
            renderer = "mermaid"
            reason = "explicit sequence diagram"
        else:
            # simple heuristics: if any edge label contains '->' or steps, choose mermaid
            edge_labels = " ".join([e.get("label", "") for e in (struct.edges or [])])
            if any(k in edge_labels for k in ("->", "step", "then", "requests", "reads", "writes")):
                renderer = "mermaid"
                reason = "edge labels indicate sequence/flow"
            else:
                renderer = "structurizr"
                reason = "default architecture renderer"

    # Translate and render
    if renderer == "mermaid":
        inp = structural_to_mermaid(struct)
        try:
            # lazy import to avoid heavy deps at module import time
            from src.renderers.mermaid_renderer import render_mermaid_svg as _render_mermaid_svg

            svg = _render_mermaid_svg(inp)
            ok = True
        except Exception:
            ok, svg = fake_renderers.render_mermaid(inp)
    elif renderer == "structurizr":
        # prefer a conversion pipeline that yields SVG: StructuralIR -> PlantUML -> SVG
        try:
            from src.renderers.structurizr_renderer import render_structurizr_svg_from_structural

            svg = render_structurizr_svg_from_structural(struct)
            ok = True
        except Exception:
            inp = structural_to_structurizr(struct)
            ok, svg = fake_renderers.render_structurizr(inp)
    else:
        inp = structural_to_plantuml(struct)
        ok, svg = fake_renderers.render_plantuml(inp)

    return svg, RendererChoice(renderer=renderer, reason=reason)
