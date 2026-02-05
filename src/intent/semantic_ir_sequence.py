"""Intent-specific semantic IR for sequence/flow diagrams."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


class SequenceParticipant(BaseModel):
    id: str
    label: str


class SequenceStep(BaseModel):
    id: str
    from_: str
    to: str
    message: Optional[str] = None
    order: int


class SequenceSemanticIR(BaseModel):
    intent: str = "sequence"
    participants: List[SequenceParticipant] = []
    steps: List[SequenceStep] = []

    def to_dict(self) -> dict:
        return self.model_dump(by_alias=True)
