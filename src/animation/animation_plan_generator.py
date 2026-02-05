"""Infer a deterministic animation plan from parsed SVG nodes/edges."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from src.animation.svg_parser import ParsedSvg, NodeInfo, EdgeInfo


@dataclass
class AnimationStep:
    selector: str
    role: str  # "node" | "edge"
    delay: float
    duration: float


@dataclass
class AnimationPlan:
    steps: List[AnimationStep]
    total_duration: float


def _sort_nodes(nodes: List[NodeInfo]) -> List[NodeInfo]:
    has_steps = any(n.step is not None for n in nodes)
    if has_steps:
        return sorted(nodes, key=lambda n: (n.step if n.step is not None else 10**9, n.center[0], n.center[1]))
    return sorted(nodes, key=lambda n: (n.center[0], n.center[1], n.label))


def _sort_edges(edges: List[EdgeInfo]) -> List[EdgeInfo]:
    return sorted(edges, key=lambda e: (e.center[1], e.center[0]))


def generate_animation_plan(
    parsed: ParsedSvg,
    node_duration: float = 1.5,
    edge_duration: float = 2.0,
    gap: float = 0.1,
) -> AnimationPlan:
    """Create an animation plan with sequential node highlight and edge flow steps.
    
    Animations use short staggered delays to create a wave effect while
    all running infinitely once started.
    """
    nodes = _sort_nodes(parsed.nodes)
    edges = _sort_edges(parsed.edges)

    steps: List[AnimationStep] = []
    cursor = 0.0

    # Stagger nodes with small delays for wave effect
    for node in nodes:
        steps.append(AnimationStep(selector=node.selector, role="node", delay=cursor, duration=node_duration))
        cursor += gap  # Small stagger between nodes
    
    # Stagger edges after nodes
    for edge in edges:
        steps.append(AnimationStep(selector=edge.selector, role="edge", delay=cursor, duration=edge_duration))
        cursor += gap

    return AnimationPlan(steps=steps, total_duration=cursor)
