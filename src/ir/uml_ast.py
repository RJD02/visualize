from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import hashlib

@dataclass
class UMLActor:
    id: str
    name: str

@dataclass
class UMLComponent:
    id: str
    name: str
    stereotype: Optional[str] = None

@dataclass
class UMLPackage:
    id: str
    name: str
    children: List[str] = field(default_factory=list)

@dataclass
class UMLRelationship:
    source: str
    target: str
    arrow: str = "--"
    label: Optional[str] = None

@dataclass
class UMLModel:
    id: str
    title: str
    actors: List[UMLActor] = field(default_factory=list)
    components: List[UMLComponent] = field(default_factory=list)
    packages: List[UMLPackage] = field(default_factory=list)
    relationships: List[UMLRelationship] = field(default_factory=list)

    def to_plantuml(self, diagram_type: str = "context") -> str:
        parts: list[str] = ["@startuml", f"title {self.title or 'Architecture Diagram'}"]
        # stable ordering
        for a in sorted(self.actors, key=lambda x: x.id):
            parts.append(f'actor "{a.name}" as {a.id}')

        for pkg in sorted(self.packages, key=lambda p: p.id):
            parts.append(f'package "{pkg.name}" as {pkg.id} {{')
            for child in sorted(pkg.children):
                comp = next((c for c in self.components if c.id == child), None)
                if comp:
                    parts.append(f'  component "{comp.name}" as {comp.id}')
            parts.append('}')

        pkg_children = {c for p in self.packages for c in p.children}
        for c in sorted(self.components, key=lambda x: x.id):
            if c.id in pkg_children:
                continue
            parts.append(f'component "{c.name}" as {c.id}')

        rels = sorted(self.relationships, key=lambda r: (r.source, r.target, r.label or ""))
        for r in rels:
            lbl = f' : {r.label}' if r.label else ""
            parts.append(f'{r.source} {r.arrow} {r.target}{lbl}')

        parts.append("@enduml")
        plant = "\n".join(parts)
        # add fingerprint for determinism/debugging
        plant = plant + "\n' fingerprint: " + hashlib.sha256(plant.encode("utf-8")).hexdigest()[:8]
        return plant
