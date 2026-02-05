"""File storage tool."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from src.utils.config import settings
from src.utils.file_utils import ensure_dir
from src.utils.file_utils import read_text_file


def save_json(name: str, payload: Dict[str, Any]) -> str:
    output_dir = ensure_dir(settings.output_dir)
    path = Path(output_dir) / name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


def save_text(name: str, text: str) -> str:
    output_dir = ensure_dir(settings.output_dir)
    path = Path(output_dir) / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def load_json(name: str) -> Dict[str, Any]:
    output_dir = ensure_dir(settings.output_dir)
    path = Path(output_dir) / name
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return json.loads(read_text_file(str(path)))


def load_text(name: str) -> str:
    output_dir = ensure_dir(settings.output_dir)
    path = Path(output_dir) / name
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return read_text_file(str(path))
