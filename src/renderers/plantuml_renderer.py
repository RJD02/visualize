"""PlantUML renderer wrapper for RendererIR."""
from __future__ import annotations

from pathlib import Path

from src.renderer import render_plantuml_svg
from src.renderers.neutral_svg import strip_svg_colors, validate_neutral_svg


def render_plantuml_svg_text(plantuml_text: str, output_name: str = "renderer_plantuml") -> str:
    svg_path = Path(render_plantuml_svg(plantuml_text, output_name))
    svg_text = svg_path.read_text(encoding="utf-8")
    svg_text = strip_svg_colors(svg_text)
    validate_neutral_svg(svg_text)
    return svg_text
