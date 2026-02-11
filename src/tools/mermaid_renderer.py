"""Helpers for rendering Mermaid diagrams supplied by the planner/LLM."""
from __future__ import annotations

from pathlib import Path

from src.renderers.mermaid_renderer import render_mermaid_svg
from src.tools.diagram_validator import validate_and_sanitize
from src.utils.config import settings
from src.utils.file_utils import ensure_dir


def render_llm_mermaid(diagram_text: str, output_name: str) -> dict:
    """Validate and render an LLM-provided Mermaid diagram.

    Returns the SVG text along with the file path and validator warnings so
    callers can persist audits.
    """
    validation = validate_and_sanitize(diagram_text, "mermaid")
    svg_text = render_mermaid_svg(validation.sanitized_text)
    output_dir = ensure_dir(settings.output_dir)
    base_path = Path(output_dir) / output_name
    mmd_path = base_path.with_suffix(".mmd")
    svg_path = base_path.with_suffix(".svg")
    mmd_path.write_text(validation.sanitized_text, encoding="utf-8")
    svg_path.write_text(svg_text, encoding="utf-8")
    return {
        "file_path": str(svg_path),
        "source_path": str(mmd_path),
        "sanitized_text": validation.sanitized_text,
        "warnings": validation.warnings,
        "svg_text": svg_text,
    }
