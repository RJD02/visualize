"""SDXL inference tool (Hugging Face)."""
from __future__ import annotations

from src.sdxl_agent import render_sdxl_image


def run_sdxl(prompt: str, output_name: str) -> str:
    return render_sdxl_image(prompt, output_name)


def run_sdxl_edit(prompt: str, output_name: str) -> str:
    """Best-effort edit using SDXL text-to-image with strong constraints."""
    return render_sdxl_image(prompt, output_name)
