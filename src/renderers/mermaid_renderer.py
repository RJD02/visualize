"""Mermaid renderer using dockerized mermaid-cli."""
from __future__ import annotations

import tempfile
from pathlib import Path

from src.renderers.docker_client import run_docker_renderer
from src.renderers.neutral_svg import strip_svg_colors, validate_neutral_svg
from src.utils.config import settings


def render_mermaid_svg(mermaid_text: str) -> str:
    with tempfile.TemporaryDirectory() as tmp_dir:
        workdir = Path(tmp_dir)
        input_path = workdir / "input.mmd"
        output_path = workdir / "output.svg"
        input_path.write_text(mermaid_text, encoding="utf-8")
        run_docker_renderer(
            settings.mermaid_renderer_image,
            workdir,
            ["input.mmd", "output.svg"],
        )
        svg_text = output_path.read_text(encoding="utf-8")
    svg_text = strip_svg_colors(svg_text)
    validate_neutral_svg(svg_text)
    return svg_text
