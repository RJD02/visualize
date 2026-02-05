"""Renderer router and orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from src.renderers.renderer_ir import RendererIR
from src.renderers.translator import ir_to_mermaid, ir_to_plantuml, ir_to_structurizr_dsl
from src.renderers.mermaid_renderer import render_mermaid_svg
from src.renderers.structurizr_renderer import render_structurizr_svg
from src.renderers.plantuml_renderer import render_plantuml_svg_text


@dataclass(frozen=True)
class RendererChoice:
    renderer: str
    reason: str


def choose_renderer(ir: RendererIR, override: Optional[str] = None) -> RendererChoice:
    if override:
        return RendererChoice(renderer=override, reason="override")

    kind = (ir.diagram_kind or "").lower()
    if kind in {"sequence", "flow", "story"}:
        return RendererChoice(renderer="mermaid", reason=f"diagram_kind={kind}")
    if kind in {"architecture", "system", "container", "component"}:
        return RendererChoice(renderer="structurizr", reason=f"diagram_kind={kind}")

    node_kinds = {n.kind.lower() for n in ir.nodes}
    if node_kinds & {"person", "system", "container", "component", "database", "external", "service", "api"}:
        return RendererChoice(renderer="structurizr", reason="node kinds indicate architecture")

    return RendererChoice(renderer="plantuml", reason="default to plantuml")


def render_ir(ir: RendererIR, override: Optional[str] = None) -> Tuple[str, RendererChoice]:
    choice = choose_renderer(ir, override=override)
    if choice.renderer == "mermaid":
        mermaid_text = ir_to_mermaid(ir)
        svg = render_mermaid_svg(mermaid_text)
        return svg, choice
    if choice.renderer == "structurizr":
        dsl = ir_to_structurizr_dsl(ir)
        svg = render_structurizr_svg(dsl)
        return svg, choice
    plantuml_text = ir_to_plantuml(ir)
    svg = render_plantuml_svg_text(plantuml_text)
    return svg, choice
