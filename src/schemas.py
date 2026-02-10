"""Pydantic schemas for API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


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
    diagram_type: Optional[str] = None
    ir_id: Optional[UUID] = None
    ir_svg_text: Optional[str] = None
    ir_metadata: Optional[dict] = None


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
    plans: List[PlanSummaryResponse] = Field(default_factory=list)


class PlanSummaryResponse(BaseModel):
    id: UUID
    session_id: UUID
    intent: str
    plan_json: Any
    metadata: Optional[dict]
    executed: bool
    created_at: datetime


class PlanExecutionResponse(BaseModel):
    id: UUID
    step_index: int
    tool_name: str
    arguments: Optional[dict]
    output: Optional[dict]
    audit_id: Optional[UUID]
    duration_ms: Optional[int]
    created_at: datetime


class StylingAuditResponse(BaseModel):
    id: UUID
    session_id: UUID
    plan_id: Optional[UUID]
    diagram_id: Optional[UUID]
    diagram_type: Optional[str]
    mode: str
    timestamp: datetime
    user_prompt: Optional[str]
    llm_format: Optional[str]
    llm_diagram: Optional[str]
    sanitized_diagram: Optional[str]
    extracted_intent: Optional[dict]
    styling_plan: Optional[dict]
    execution_steps: List[str]
    agent_reasoning: Optional[str]
    renderer_input_before: Optional[str]
    renderer_input_after: Optional[str]
    svg_before: Optional[str]
    svg_after: Optional[str]
    validation_warnings: Optional[List[str]]
    blocked_tokens: Optional[List[str]]


class PlanHistoryResponse(BaseModel):
    id: UUID
    session_id: UUID
    intent: str
    plan_json: Any
    metadata: Optional[dict]
    executed: bool
    created_at: datetime
    executions: List[PlanExecutionResponse]
    audits: List[StylingAuditResponse]


class MCPToolMetadata(BaseModel):
    id: str
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    side_effects: Optional[str] = None
    mode: Optional[str] = None
    version: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MCPDiscoverResponse(BaseModel):
    tools: List[MCPToolMetadata]


class MCPExecuteRequest(BaseModel):
    tool_id: str
    args: Dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[UUID] = None
    plan_id: Optional[UUID] = None


class MCPExecuteResponse(BaseModel):
    result: Dict[str, Any]
    audit_id: Optional[UUID] = None
