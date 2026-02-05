"""Structural IR for renderer-agnostic diagrams."""
from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class StructuralNode(BaseModel):
    id: str
    kind: str = "service"
    label: Optional[str] = None
    group: Optional[str] = None


class StructuralEdge(BaseModel):
    from_: str = Field(..., alias="from")
    to: str
    type: str = "interaction"
    label: Optional[str] = None
    order: Optional[int] = None


class StructuralGroup(BaseModel):
    id: str
    label: Optional[str] = None
    members: List[str] = []


class StructuralIR(BaseModel):
    diagram_kind: str = "generic"
    layout: Literal["left-to-right", "top-down"] = "left-to-right"
    title: Optional[str] = None
    nodes: List[StructuralNode] = []
    edges: List[StructuralEdge] = []
    groups: List[StructuralGroup] = []

    model_config = {
        "populate_by_name": True,
    }

    def normalized(self) -> "StructuralIR":
        nodes = sorted(self.nodes, key=lambda n: n.id)
        edges = sorted(self.edges, key=lambda e: (e.from_, e.to, e.type, e.label or "", e.order or 0))
        groups = sorted(self.groups, key=lambda g: g.id)
        return StructuralIR(
            diagram_kind=self.diagram_kind,
            layout=self.layout,
            title=self.title,
            nodes=nodes,
            edges=edges,
            groups=groups,
        )

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True)
