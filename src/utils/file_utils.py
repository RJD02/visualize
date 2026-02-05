"""File utilities."""
from __future__ import annotations

from pathlib import Path


def ensure_dir(path: str) -> Path:
    """Ensure directory exists and return Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_text_file(path: str) -> str:
    """Read a text file as UTF-8."""
    return Path(path).read_text(encoding="utf-8")
