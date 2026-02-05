"""Input parsing and text extraction."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from docx import Document
from pypdf import PdfReader


def _read_docx(path: Path) -> str:
    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
    return "\n".join(parts)


def parse_files(file_paths: Iterable[str]) -> str:
    """Parse multiple files (.py/.js/.docx/etc.) into a single text blob."""
    parts = []
    for fp in file_paths:
        path = Path(fp)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {fp}")
        header = f"\n# File: {path.name}\n"
        suffix = path.suffix.lower()
        if suffix == ".docx":
            content = _read_docx(path)
        elif suffix == ".pdf":
            content = _read_pdf(path)
        else:
            content = _read_text(path)
        parts.append(header + content)
    return "\n".join(parts)
