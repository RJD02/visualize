"""Pydantic schemas for API."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class SessionCreateResponse(BaseModel):
    session_id: UUID
    title: str


class MessageCreate(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    intent: Optional[str]
    image_id: Optional[UUID]
    message_type: Optional[str]
    image_version: Optional[int]
    diagram_type: Optional[str]
    created_at: datetime


class ImageResponse(BaseModel):
    id: UUID
    version: int
    file_path: str
    prompt: Optional[str]
    reason: Optional[str]
    created_at: datetime


class ArchitecturePlanResponse(BaseModel):
    data: dict
    created_at: datetime


class DiagramFileResponse(BaseModel):
    diagram_type: str
    file_path: str
    created_at: datetime


class ImageIRResponse(BaseModel):
    image_id: UUID
    diagram_type: Optional[str]
    svg_text: str


class SessionDetailResponse(BaseModel):
    session_id: UUID
    title: str
    source_repo: Optional[str] = None
    source_commit: Optional[str] = None
    architecture_plan: Optional[ArchitecturePlanResponse]
    images: List[ImageResponse]
    diagrams: List[DiagramFileResponse]
    messages: List[MessageResponse]
