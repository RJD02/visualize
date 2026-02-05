"""Map intent-specific semantic IR to structural renderer IR."""
from __future__ import annotations

import re
from typing import List, Tuple

from src.models.architecture_plan import ArchitecturePlan
from src.ir.structural_ir import StructuralIR, StructuralNode, StructuralEdge, StructuralGroup
from src.intent.semantic_ir_architecture import ArchitectureSemanticIR, ArchitectureActor, ArchitectureElement, ArchitectureRelationship
from src.intent.semantic_ir_story import StorySemanticIR, StoryCharacter, StoryEvent, StoryLocation, StoryTransition
from src.intent.semantic_ir_sequence import SequenceSemanticIR, SequenceParticipant, SequenceStep


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip())
    if not cleaned:
        return "node"
    if not cleaned[0].isalpha():
        cleaned = f"n_{cleaned}"
    return cleaned


def architecture_ir_from_plan(plan: ArchitecturePlan, diagram_type: str) -> ArchitectureSemanticIR:
    def _limit(items: List[str], count: int) -> List[str]:
        return items[:count] if count > 0 else items

    actors_raw = list(plan.zones.clients)
    services_raw = list(plan.zones.core_services)
    edge_raw = list(plan.zones.edge)
    externals_raw = list(plan.zones.external_services)
    stores_raw = list(plan.zones.data_stores)

    if diagram_type == "system_context":
        actors_raw = _limit(actors_raw, 1)
        edge_raw = _limit(edge_raw, 1)
        services_raw = _limit(services_raw, 1)
        externals_raw = _limit(externals_raw, 1)
        stores_raw = _limit(stores_raw, 1)
    elif diagram_type == "container":
        actors_raw = _limit(actors_raw, 1)
        externals_raw = []
    elif diagram_type == "component":
        actors_raw = []
        edge_raw = []
        externals_raw = []
        stores_raw = []

    actors = [ArchitectureActor(id=_slug(a), label=a) for a in actors_raw]
    services = [ArchitectureElement(id=_slug(s), label=s, kind="service") for s in services_raw]
    edge = [ArchitectureElement(id=_slug(s), label=s, kind="service") for s in edge_raw]
    externals = [ArchitectureElement(id=_slug(s), label=s, kind="external") for s in externals_raw]
    stores = [ArchitectureElement(id=_slug(s), label=s, kind="database") for s in stores_raw]

    allowed_ids = {a.id for a in actors} | {s.id for s in services} | {s.id for s in edge} | {s.id for s in externals} | {s.id for s in stores}
    relationships = []
    for rel in plan.relationships:
        from_id = _slug(rel.from_)
        to_id = _slug(rel.to)
        if from_id in allowed_ids and to_id in allowed_ids:
            relationships.append(ArchitectureRelationship(from_=from_id, to=to_id, type=rel.type, description=rel.description))

    systems = edge + externals

    return ArchitectureSemanticIR(
        diagram_type=diagram_type,
        actors=actors,
        systems=systems,
        services=services,
        data_stores=stores,
        relationships=relationships,
    )


def architecture_to_structural(ir: ArchitectureSemanticIR) -> StructuralIR:
    nodes: List[StructuralNode] = []
    edges: List[StructuralEdge] = []
    groups: List[StructuralGroup] = []

    group_map = {
        "actors": ("person", ir.actors),
        "systems": ("system", ir.systems),
        "services": ("service", ir.services),
        "data_stores": ("database", ir.data_stores),
    }

    for group_id, (kind, items) in group_map.items():
        if not items:
            continue
        members = []
        for item in items:
            label = item.label
            node_id = item.id
            nodes.append(StructuralNode(id=node_id, kind=kind, label=label, group=group_id))
            members.append(node_id)
        groups.append(StructuralGroup(id=group_id, label=group_id.replace("_", " "), members=members))

    for rel in ir.relationships:
        edges.append(StructuralEdge(**{"from": rel.from_, "to": rel.to, "type": rel.type, "label": rel.description}))

    return StructuralIR(
        diagram_kind="architecture",
        layout="left-to-right",
        title=None,
        nodes=nodes,
        edges=edges,
        groups=groups,
    )


def story_ir_from_text(text: str) -> StorySemanticIR:
    sentences = [s.strip() for s in re.split(r"[.!?]+", text or "") if s.strip()]
    title = sentences[0] if sentences else "Story"

    names = sorted({m.group(0) for m in re.finditer(r"\b[A-Z][a-z]+\b", text or "")})
    characters = [StoryCharacter(id=_slug(n), name=n) for n in names if len(n) > 2]

    locations = []
    for m in re.finditer(r"\b(?:at|in|on)\s+([A-Z][a-zA-Z\s]+)", text or ""):
        loc = m.group(1).strip().split(" ")[0:3]
        loc_name = " ".join(loc)
        locations.append(loc_name)
    locations = sorted(set(locations))
    location_objs = [StoryLocation(id=_slug(l), name=l) for l in locations]

    events = []
    transitions = []
    for idx, sentence in enumerate(sentences):
        event_id = f"event_{idx+1}"
        events.append(StoryEvent(id=event_id, summary=sentence))
        if idx > 0:
            transitions.append(StoryTransition(from_=f"event_{idx}", to=event_id, label=None))

    return StorySemanticIR(
        title=title,
        characters=characters,
        locations=location_objs,
        events=events,
        transitions=transitions,
    )


def story_to_structural(ir: StorySemanticIR) -> StructuralIR:
    nodes = [StructuralNode(id=e.id, kind="event", label=e.summary) for e in ir.events]
    edges = [StructuralEdge(**{"from": t.from_, "to": t.to, "type": "transition", "label": t.label}) for t in ir.transitions]
    return StructuralIR(
        diagram_kind="flow",
        layout="top-down",
        title=ir.title,
        nodes=nodes,
        edges=edges,
        groups=[],
    )


def sequence_ir_from_text(text: str) -> SequenceSemanticIR:
    arrows = re.findall(r"(\w+)\s*->\s*(\w+)", text or "")
    participants = []
    steps = []
    seen = {}

    def _ensure_participant(name: str) -> str:
        key = _slug(name)
        if key not in seen:
            seen[key] = name
            participants.append(SequenceParticipant(id=key, label=name))
        return key

    if arrows:
        for idx, (src, dst) in enumerate(arrows, start=1):
            src_id = _ensure_participant(src)
            dst_id = _ensure_participant(dst)
            steps.append(SequenceStep(id=f"step_{idx}", from_=src_id, to=dst_id, message=None, order=idx))
    else:
        tokens = re.split(r"->", text or "")
        for idx, part in enumerate([t.strip() for t in tokens if t.strip()]):
            _ensure_participant(part)
        for idx in range(len(participants) - 1):
            steps.append(SequenceStep(id=f"step_{idx+1}", from_=participants[idx].id, to=participants[idx+1].id, message=None, order=idx+1))

    return SequenceSemanticIR(participants=participants, steps=steps)


def sequence_to_structural(ir: SequenceSemanticIR) -> StructuralIR:
    nodes = [StructuralNode(id=p.id, kind="participant", label=p.label) for p in ir.participants]
    edges = [StructuralEdge(**{"from": s.from_, "to": s.to, "type": "message", "label": s.message, "order": s.order}) for s in ir.steps]
    return StructuralIR(
        diagram_kind="sequence",
        layout="left-to-right",
        title=None,
        nodes=nodes,
        edges=edges,
        groups=[],
    )
