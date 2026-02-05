"""Structurizr renderer using dockerized CLI."""
from __future__ import annotations

import tempfile
from pathlib import Path

from src.renderers.docker_client import run_docker_renderer
from src.renderers.neutral_svg import strip_svg_colors, validate_neutral_svg
from src.utils.config import settings


def render_structurizr_svg(dsl_text: str) -> str:
    with tempfile.TemporaryDirectory() as tmp_dir:
        workdir = Path(tmp_dir)
        input_path = workdir / "workspace.json"
        input_path.write_text(dsl_text, encoding="utf-8")
        run_docker_renderer(
            settings.structurizr_renderer_image,
            workdir,
            ["workspace.json"],
        )
        pumls = sorted(workdir.glob("*.puml"))
        if not pumls:
            raise ValueError("No PlantUML output from Structurizr renderer")
        plantuml_text = pumls[0].read_text(encoding="utf-8")
    from src.renderers.plantuml_renderer import render_plantuml_svg_text

    svg_text = render_plantuml_svg_text(plantuml_text, output_name="structurizr")
    svg_text = strip_svg_colors(svg_text)
    validate_neutral_svg(svg_text)
    return svg_text
