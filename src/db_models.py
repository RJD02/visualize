"""SQLAlchemy models for sessions, messages, images."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), default="Architecture Session")
    input_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_repo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_commit: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    images = relationship("Image", back_populates="session", cascade="all, delete-orphan")
    plans = relationship("ArchitecturePlan", back_populates="session", cascade="all, delete-orphan")
    diagrams = relationship("DiagramFile", back_populates="session", cascade="all, delete-orphan")
    ir_versions = relationship("DiagramIR", back_populates="session", cascade="all, delete-orphan")
    styling_audits = relationship("StylingAudit", back_populates="session", cascade="all, delete-orphan")
    plan_records = relationship("PlanRecord", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    image_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    message_type: Mapped[str] = mapped_column(String(16), default="text")
    image_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diagram_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ir_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="messages")


class ArchitecturePlan(Base):
    __tablename__ = "architecture_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="plans")


class PlanRecord(Base):
    __tablename__ = "plan_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    intent: Mapped[str] = mapped_column(String(64))
    plan_json: Mapped[dict] = mapped_column(JSON)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    executed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="plan_records")
    executions = relationship("PlanExecution", back_populates="plan", cascade="all, delete-orphan")
    audits = relationship("StylingAudit", back_populates="plan")


class PlanExecution(Base):
    __tablename__ = "plan_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plan_records.id"))
    step_index: Mapped[int] = mapped_column(Integer)
    tool_name: Mapped[str] = mapped_column(String(128))
    arguments: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    audit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    plan = relationship("PlanRecord", back_populates="executions")


class Image(Base):
    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    version: Mapped[int] = mapped_column(Integer)
    parent_image_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500))
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_repo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_commit: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ir_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="images")
    audits = relationship("StylingAudit", back_populates="diagram", cascade="all, delete-orphan")


class DiagramFile(Base):
    __tablename__ = "diagram_files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    diagram_type: Mapped[str] = mapped_column(String(64))
    file_path: Mapped[str] = mapped_column(String(500))
    source_repo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_commit: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="diagrams")


class DiagramIR(Base):
    __tablename__ = "diagram_ir_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    diagram_type: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    parent_ir_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    svg_text: Mapped[str] = mapped_column(Text)
    ir_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    plantuml_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="ir_versions")


class StylingAudit(Base):
    __tablename__ = "styling_audits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("plan_records.id"), nullable=True)
    diagram_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("images.id"), nullable=True)
    diagram_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_format: Mapped[str | None] = mapped_column(String(16), nullable=True)
    llm_diagram: Mapped[str | None] = mapped_column(Text, nullable=True)
    sanitized_diagram: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_intent: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    styling_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_warnings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    blocked_tokens: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    execution_steps: Mapped[list[str]] = mapped_column(JSON, default=list)
    renderer_input_before: Mapped[str | None] = mapped_column(Text, nullable=True)
    renderer_input_after: Mapped[str | None] = mapped_column(Text, nullable=True)
    svg_before: Mapped[str | None] = mapped_column(Text, nullable=True)
    svg_after: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(String(16), default="post-svg")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="styling_audits")
    diagram = relationship("Image", back_populates="audits")
    plan = relationship("PlanRecord", back_populates="audits")
