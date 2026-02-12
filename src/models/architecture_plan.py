"""Core ArchitecturePlan model (framework-agnostic)."""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


class Relationship(BaseModel):
    from_: str = Field(..., alias="from")
    to: str
    type: Literal["sync", "async", "data", "auth"]
    description: str


class Zones(BaseModel):
    clients: List[str] = []
    edge: List[str] = []
    core_services: List[str] = []
    external_services: List[str] = []
    data_stores: List[str] = []


class VisualHints(BaseModel):
    layout: Literal["left-to-right", "top-down"] = "left-to-right"
    group_by_zone: bool = True
    external_dashed: bool = True


class ArchitecturePlan(BaseModel):
    system_name: str
    diagram_views: List[str]
    zones: Zones
    relationships: List[Relationship]
    visual_hints: VisualHints
    diagram_kind: str | None = None
    rendering_hints: dict | None = None
    narrative: str | None = None

    model_config = {
        "populate_by_name": True,
    }
