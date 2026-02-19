
"""Canonical IR v2 schema and helpers."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from jsonschema import Draft202012Validator, ValidationError


# Edge dataclass for new IR schema
@dataclass(frozen=True)
class Edge:
    edge_id: str
    from_: str
    to: str
    relation_type: str
    direction: str
    category: str
    mode: str
    label: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "from": self.from_,
            "to": self.to,
            "relation_type": self.relation_type,
            "direction": self.direction,
            "category": self.category,
            "mode": self.mode,
            "label": self.label,
            "confidence": self.confidence,
        }


def make_edge_id() -> str:
    return f"edge-{uuid.uuid4().hex[:8]}"


IR_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["diagram_id", "ir_version", "parent_version", "ir"],
    "properties": {
        "diagram_id": {"type": "string"},
        "ir_version": {"type": "integer", "minimum": 1},
        "parent_version": {"type": ["integer", "null"], "minimum": 1},
        "ir": {
            "type": "object",
            "required": ["diagram"],
            "properties": {
                "diagram": {
                    "type": "object",
                    "required": ["id", "type", "blocks", "edges"],
                    "properties": {
                        "id": {"type": "string"},
                        "type": {"type": "string"},
                        "blocks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["id", "type", "text", "bbox"],
                                "properties": {
                                    "id": {"type": "string"},
                                    "type": {"type": "string"},
                                    "text": {"type": "string"},
                                    "bbox": {
                                        "type": "object",
                                        "required": ["x", "y", "w", "h"],
                                        "properties": {
                                            "x": {"type": "number"},
                                            "y": {"type": "number"},
                                            "w": {"type": "number", "minimum": 0},
                                            "h": {"type": "number", "minimum": 0}
                                        },
                                        "additionalProperties": False
                                    },
                                    "style": {"type": "object"},
                                    "annotations": {"type": "object"},
                                    "version": {"type": "integer", "minimum": 1},
                                    "hidden": {"type": "boolean"},
                                    "zone": {"type": "string"}
                                },
                                "additionalProperties": True
                            }
                        },
                        "edges": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["edge_id", "from", "to", "relation_type", "direction", "category", "mode", "label", "confidence"],
                                "properties": {
                                    "edge_id": {"type": "string"},
                                    "from": {"type": "string"},
                                    "to": {"type": "string"},
                                    "relation_type": {"type": "string"},
                                    "direction": {"type": "string", "enum": ["unidirectional", "bidirectional"]},
                                    "category": {"type": "string", "enum": ["data_flow", "user_traffic", "replication", "auth", "secret_distribution", "monitoring", "control", "metadata", "network"]},
                                    "mode": {"type": "string", "enum": ["sync", "async", "broadcast", "conditional"]},
                                    "label": {"type": "string"},
                                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                                },
                                "additionalProperties": True
                            }
                        },
                        "global_intent": {"type": "object"}
                    },
                    "additionalProperties": True
                }
            },
            "additionalProperties": True
        }
    },
    "additionalProperties": False
}

_VALIDATOR = Draft202012Validator(IR_SCHEMA)


@dataclass(frozen=True)
class IRVersion:
    diagram_id: str
    ir_version: int
    parent_version: Optional[int]
    ir: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diagram_id": self.diagram_id,
            "ir_version": self.ir_version,
            "parent_version": self.parent_version,
            "ir": self.ir,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def validate_ir(payload: Dict[str, Any]) -> None:
    try:
        _VALIDATOR.validate(payload)
    except ValidationError as exc:
        raise ValueError(f"IR validation failed: {exc.message}") from exc


def from_json(text: str) -> IRVersion:
    payload = json.loads(text)
    validate_ir(payload)
    return IRVersion(
        diagram_id=payload["diagram_id"],
        ir_version=int(payload["ir_version"]),
        parent_version=payload.get("parent_version"),
        ir=payload["ir"],
    )


def to_json(payload: Dict[str, Any]) -> str:
    validate_ir(payload)
    return json.dumps(payload, indent=2)


def bump_version(current: int | None) -> int:
    return 1 if current is None else int(current) + 1


def upgrade_to_v2(ir_payload: Dict[str, Any], *, diagram_id: Optional[str] = None) -> IRVersion:
    if {
        "diagram_id",
        "ir_version",
        "parent_version",
        "ir",
    }.issubset(ir_payload.keys()):
        validate_ir(ir_payload)
        return IRVersion(
            diagram_id=ir_payload["diagram_id"],
            ir_version=int(ir_payload["ir_version"]),
            parent_version=ir_payload.get("parent_version"),
            ir=ir_payload["ir"],
        )

    diagram = ir_payload.get("diagram") if isinstance(ir_payload, dict) else None
    if not diagram:
        diagram = {
            "id": diagram_id or "diagram",
            "type": ir_payload.get("diagram_type", "diagram"),
            "blocks": [],
            "relations": [],
        }
    wrapper = {
        "diagram_id": diagram_id or diagram.get("id") or "diagram",
        "ir_version": 1,
        "parent_version": None,
        "ir": {"diagram": diagram},
    }
    validate_ir(wrapper)
    return IRVersion(
        diagram_id=wrapper["diagram_id"],
        ir_version=wrapper["ir_version"],
        parent_version=None,
        ir=wrapper["ir"],
    )


def make_ir_version(diagram_id: str, ir: Dict[str, Any], *, parent_version: Optional[int] = None, version: Optional[int] = None) -> IRVersion:
    payload = {
        "diagram_id": diagram_id,
        "ir_version": version or bump_version(parent_version),
        "parent_version": parent_version,
        "ir": ir,
    }
    validate_ir(payload)
    return IRVersion(
        diagram_id=payload["diagram_id"],
        ir_version=payload["ir_version"],
        parent_version=payload["parent_version"],
        ir=payload["ir"],
    )


def diff_summary(before: Dict[str, Any], after: Dict[str, Any]) -> str:
    return f"blocks={len(before.get('diagram', {}).get('blocks', []))}->{len(after.get('diagram', {}).get('blocks', []))}; relations={len(before.get('diagram', {}).get('relations', []))}->{len(after.get('diagram', {}).get('relations', []))}"
