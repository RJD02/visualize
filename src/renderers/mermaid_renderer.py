"""Mermaid renderer using dockerized mermaid-cli."""
from __future__ import annotations

import tempfile
from pathlib import Path

from src.renderers.docker_client import run_docker_renderer
from src.renderers.neutral_svg import strip_svg_colors, validate_neutral_svg
from src.utils.config import settings
from src.utils.file_utils import read_text_file
from src.renderers import fake_renderers


def render_mermaid_svg(mermaid_text: str) -> str:
    with tempfile.TemporaryDirectory() as tmp_dir:
        workdir = Path(tmp_dir)
        input_path = workdir / "input.mmd"
        output_path = workdir / "output.svg"
        input_path.write_text(mermaid_text, encoding="utf-8")
        try:
            run_docker_renderer(
                settings.mermaid_renderer_image,
                workdir,
                ["input.mmd", "output.svg"],
            )
        except Exception:
            # Docker renderer not available or failed; fall back
            ok, svg_text = fake_renderers.render_mermaid(mermaid_text)
            if not ok:
                raise
        else:
            # If docker renderer ran, ensure output file was produced
            if output_path.exists():
                try:
                    svg_text = read_text_file(str(output_path))
                except Exception:
                    svg_text = None
            else:
                svg_text = None

        if svg_text is None:
            ok, svg_text = fake_renderers.render_mermaid(mermaid_text)
            if not ok:
                raise
    svg_text = strip_svg_colors(svg_text)
    validate_neutral_svg(svg_text)
    return svg_text
