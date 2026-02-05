"""Text extraction tool (docx/code)."""
from __future__ import annotations

from typing import Iterable, Optional

from src.input_parser import parse_files


def extract_text(files: Optional[Iterable[str]] = None, text: Optional[str] = None) -> str:
    if text:
        return text
    if not files:
        raise ValueError("Provide files or text")
    return parse_files(files)
