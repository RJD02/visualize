"""Intent-aware Semantic IR dataclasses.

This file provides minimal, deterministic, inspectable IR schemas for POC.
Each IR has `to_dict()` for serialization.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any


@dataclass
class ArchitectureIR:
    actors: List[Dict[str, Any]] = field(default_factory=list)
    systems: List[Dict[str, Any]] = field(default_factory=list)
    services: List[Dict[str, Any]] = field(default_factory=list)
    data_stores: List[Dict[str, Any]] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


@dataclass
class StoryIR:
    characters: List[Dict[str, Any]] = field(default_factory=list)
    locations: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    transitions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


@dataclass
class SequenceIR:
    participants: List[Dict[str, Any]] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


@dataclass
class StructuralIR:
    """A renderer-agnostic structural IR derived from semantic IR.

    Fields are intentionally generic but deterministic.
    """
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
