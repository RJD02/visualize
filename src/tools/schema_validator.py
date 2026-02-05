"""Schema validation tool."""
from __future__ import annotations

from typing import Any, Dict

from src.models.architecture_plan import ArchitecturePlan


def validate_architecture_plan(data: Dict[str, Any]) -> ArchitecturePlan:
    return ArchitecturePlan.model_validate(data)
