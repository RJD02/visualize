from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
import json

# Semantic, UML-first IR (no layout, no coordinates)
@dataclass
class Actor:
    id: str
    name: str
    tags: List[str] = field(default_factory=list)

@dataclass
class Component:
    id: str
    name: str
    type: str = "component"  # component/container/system
    tags: List[str] = field(default_factory=list)
    state: Optional[str] = None  # for future animation

@dataclass
class Interface:
    id: str
    name: str
    provides: Optional[str] = None

@dataclass
class Relationship:
    source: str
    target: str
    type: str = "association"  # association/dependency/realization/message
    label: Optional[str] = None
    direction: Optional[str] = None  # '->', '<-', None
    order: Optional[int] = None  # for sequences / animation phases
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SystemBoundary:
    id: str
    name: str
    owners: List[str] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    synthetic: bool = False

@dataclass
class SemanticIR:
    id: str
    title: str
    actors: List[Actor] = field(default_factory=list)
    components: List[Component] = field(default_factory=list)
    interfaces: List[Interface] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    boundaries: List[SystemBoundary] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, indent=2)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_json(text: str) -> "SemanticIR":
        data = json.loads(text)
        ir = SemanticIR(
            id=data["id"],
            title=data.get("title", ""),
            actors=[Actor(**a) for a in data.get("actors", [])],
            components=[Component(**c) for c in data.get("components", [])],
            interfaces=[Interface(**i) for i in data.get("interfaces", [])],
            relationships=[Relationship(**r) for r in data.get("relationships", [])],
            boundaries=[SystemBoundary(**b) for b in data.get("boundaries", [])],
            metadata=data.get("metadata", {}),
        )
        return ir
