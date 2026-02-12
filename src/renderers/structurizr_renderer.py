from __future__ import annotations

"""Structurizr renderer wrapper: convert StructuralIR -> PlantUML -> SVG.

This implementation prefers converting structural IR to PlantUML and
re-using the PlantUML rendering path to produce SVG, which avoids
requiring a dockerized structurizr image in the short term.
"""

import tempfile
from pathlib import Path
from typing import Any

from src.ir.structural_to_plantuml import structural_ir_to_plantuml
from src.renderers.plantuml_renderer import render_plantuml_svg_text
from src.renderers.docker_client import run_docker_renderer
from src.utils.config import settings
from src.utils.file_utils import read_text_file


def render_structurizr_svg_from_structural(ir: Any) -> str:
    plantuml = structural_ir_to_plantuml(ir)
    svg = render_plantuml_svg_text(plantuml, output_name="structurizr_render")
    return svg


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
        try:
            plantuml_text = read_text_file(str(pumls[0]))
        except Exception:
            plantuml_text = pumls[0].read_text(encoding="utf-8", errors="ignore")

    svg_text = render_plantuml_svg_text(plantuml_text, output_name="structurizr")
    return svg_text
