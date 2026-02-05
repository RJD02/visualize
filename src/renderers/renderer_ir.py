"""Renderer-agnostic IR for POC renderers."""
from __future__ import annotations

from typing import List, Optional, Literal

from pydantic import BaseModel, Field


class IRNode(BaseModel):
    id: str
    kind: str = "service"
    label: Optional[str] = None
    group: Optional[str] = None


class IREdge(BaseModel):
    from_: str = Field(..., alias="from")
    to: str
    type: str = "interaction"
    label: Optional[str] = None


class IRGroup(BaseModel):
    id: str
    label: Optional[str] = None
    members: List[str] = []


class RendererIR(BaseModel):
    diagram_kind: str = "generic"
    layout: Literal["left-to-right", "top-down"] = "left-to-right"
    title: Optional[str] = None
    nodes: List[IRNode] = []
    edges: List[IREdge] = []
    groups: List[IRGroup] = []

    model_config = {
        "populate_by_name": True,
    }

    def normalized(self) -> "RendererIR":
        nodes = sorted(self.nodes, key=lambda n: n.id)
        edges = sorted(self.edges, key=lambda e: (e.from_, e.to, e.type, e.label or ""))
        groups = sorted(self.groups, key=lambda g: g.id)
        return RendererIR(
            diagram_kind=self.diagram_kind,
            layout=self.layout,
            title=self.title,
            nodes=nodes,
            edges=edges,
            groups=groups,
        )

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True)
