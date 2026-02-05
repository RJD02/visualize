"""Intent-specific semantic IR for architecture diagrams."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


class ArchitectureActor(BaseModel):
    id: str
    label: str


class ArchitectureElement(BaseModel):
    id: str
    label: str
    kind: str


class ArchitectureRelationship(BaseModel):
    from_: str
    to: str
    type: str
    description: Optional[str] = None


class ArchitectureSemanticIR(BaseModel):
    intent: str = "architecture"
    diagram_type: str = "system_context"
    actors: List[ArchitectureActor] = []
    systems: List[ArchitectureElement] = []
    services: List[ArchitectureElement] = []
    data_stores: List[ArchitectureElement] = []
    relationships: List[ArchitectureRelationship] = []

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True)
