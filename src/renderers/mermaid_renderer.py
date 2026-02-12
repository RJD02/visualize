"""Mermaid renderer using dockerized mermaid-cli."""
from __future__ import annotations

import tempfile
from pathlib import Path
import subprocess

from src.utils.config import settings
from src.utils.file_utils import read_text_file


def _run_docker_mermaid_cli(workdir: Path, input_path: Path, output_path: Path) -> str:
    image = settings.mermaid_renderer_image
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{workdir}:/data",
        image,
        "-i",
        f"/data/{input_path.name}",
        "-o",
        f"/data/{output_path.name}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr or stdout or "Unknown error"
        raise RuntimeError(f"Mermaid docker render failed. cmd={' '.join(cmd)} error={detail}")
    return " ".join(cmd)


def render_mermaid_svg_with_command(mermaid_text: str) -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        workdir = Path(tmp_dir)
        input_path = workdir / "input.mmd"
        output_path = workdir / "output.svg"
        input_path.write_text(mermaid_text, encoding="utf-8")
        cmd = _run_docker_mermaid_cli(workdir, input_path, output_path)
        if output_path.exists():
            try:
                svg_text = read_text_file(str(output_path))
            except Exception:
                svg_text = output_path.read_text(encoding="utf-8", errors="ignore")
        else:
            raise ValueError("Mermaid renderer did not produce output.svg")
    return svg_text, cmd


def render_mermaid_svg(mermaid_text: str) -> str:
    svg_text, _ = render_mermaid_svg_with_command(mermaid_text)
    return svg_text
