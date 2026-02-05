"""Semantic Aesthetic IR (no concrete visuals)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


ALLOWED_MOODS = {"minimal", "vibrant", "calm", "energetic"}
ALLOWED_CONTRAST = {"low", "medium", "high"}
ALLOWED_DENSITY = {"compact", "spacious"}
ALLOWED_IMPORTANCE = {"primary", "secondary", "neutral"}
ALLOWED_ATTENTION = {"focus", "normal", "deemphasize"}
ALLOWED_STABILITY = {"stable", "dynamic", "neutral"}
ALLOWED_ACTIVITY = {"active", "passive", "neutral"}
ALLOWED_CRITICALITY = {"high", "medium", "low", "neutral"}


@dataclass
class GlobalIntent:
    mood: str = "minimal"
    contrast: str = "medium"
    density: str = "compact"


@dataclass
class NodeIntent:
    importance: str = "neutral"
    attention: str = "normal"
    stability: str = "neutral"


@dataclass
class EdgeIntent:
    activity: str = "neutral"
    criticality: str = "neutral"


@dataclass
class SemanticAestheticIR:
    globalIntent: GlobalIntent = field(default_factory=GlobalIntent)
    nodeIntent: Dict[str, NodeIntent] = field(default_factory=dict)
    edgeIntent: Dict[str, EdgeIntent] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "SemanticAestheticIR":
        global_data = (data or {}).get("globalIntent") or {}
        global_intent = GlobalIntent(
            mood=global_data.get("mood", "minimal"),
            contrast=global_data.get("contrast", "medium"),
            density=global_data.get("density", "compact"),
        )
        if global_intent.mood not in ALLOWED_MOODS:
            global_intent.mood = "minimal"
        if global_intent.contrast not in ALLOWED_CONTRAST:
            global_intent.contrast = "medium"
        if global_intent.density not in ALLOWED_DENSITY:
            global_intent.density = "compact"

        node_intent: Dict[str, NodeIntent] = {}
        for key, value in (data or {}).get("nodeIntent", {}).items():
            node = NodeIntent(
                importance=(value or {}).get("importance", "neutral"),
                attention=(value or {}).get("attention", "normal"),
                stability=(value or {}).get("stability", "neutral"),
            )
            if node.importance not in ALLOWED_IMPORTANCE:
                node.importance = "neutral"
            if node.attention not in ALLOWED_ATTENTION:
                node.attention = "normal"
            if node.stability not in ALLOWED_STABILITY:
                node.stability = "neutral"
            node_intent[key] = node

        edge_intent: Dict[str, EdgeIntent] = {}
        for key, value in (data or {}).get("edgeIntent", {}).items():
            edge = EdgeIntent(
                activity=(value or {}).get("activity", "neutral"),
                criticality=(value or {}).get("criticality", "neutral"),
            )
            if edge.activity not in ALLOWED_ACTIVITY:
                edge.activity = "neutral"
            if edge.criticality not in ALLOWED_CRITICALITY:
                edge.criticality = "neutral"
            edge_intent[key] = edge

        return SemanticAestheticIR(
            globalIntent=global_intent,
            nodeIntent=node_intent,
            edgeIntent=edge_intent,
            metadata=(data or {}).get("metadata", {}),
        )
