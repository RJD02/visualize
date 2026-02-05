"""Intent-specific semantic IR for story/narrative diagrams."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


class StoryCharacter(BaseModel):
    id: str
    name: str


class StoryLocation(BaseModel):
    id: str
    name: str


class StoryEvent(BaseModel):
    id: str
    summary: str
    participants: List[str] = []
    location: Optional[str] = None


class StoryTransition(BaseModel):
    from_: str
    to: str
    label: Optional[str] = None


class StorySemanticIR(BaseModel):
    intent: str = "story"
    title: Optional[str] = None
    characters: List[StoryCharacter] = []
    locations: List[StoryLocation] = []
    events: List[StoryEvent] = []
    transitions: List[StoryTransition] = []

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True)
