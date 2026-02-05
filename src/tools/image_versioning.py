"""Image versioning tool."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from src.utils.config import settings
from src.utils.file_utils import ensure_dir
from src.utils.file_utils import read_text_file


def _manifest_path(name: str) -> Path:
    output_dir = ensure_dir(settings.output_dir)
    return Path(output_dir) / f"{name}_images.json"


def load_versions(name: str) -> List[Dict[str, str]]:
    path = _manifest_path(name)
    if not path.exists():
        return []
    return json.loads(read_text_file(str(path)))


def add_version(name: str, image_file: str) -> List[Dict[str, str]]:
    versions = load_versions(name)
    version = len(versions) + 1
    versions.append({"version": version, "file": image_file})
    _manifest_path(name).write_text(json.dumps(versions, indent=2), encoding="utf-8")
    return versions


def set_versions(name: str, versions: List[Dict[str, str]]) -> None:
    _manifest_path(name).write_text(json.dumps(versions, indent=2), encoding="utf-8")
