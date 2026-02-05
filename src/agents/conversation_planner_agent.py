"""Conversation planner agent to produce execution plans."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from openai import OpenAI

from src.utils.config import settings


PLANNER_SYSTEM = (
    "You are a conversation planning agent for an architecture assistant. "
    "Your job is to convert a user message into a structured execution plan. "
    "You MUST choose from the provided MCP tools. "
    "Use ONLY JSON and match this schema:\n"
    "{\n"
    "  \"intent\": \"explain|edit_image|diagram_change|regenerate|clarify|generate_sequence\",\n"
    "  \"diagram_count\": number or null,\n"
    "  \"diagrams\": [\n"
    "    {\"type\": \"system_context|container|component|sequence|other\", \"reason\": \"string\"}\n"
    "  ],\n"
    "  \"target_image_id\": \"uuid or null\",\n"
    "  \"target_diagram_type\": \"system_context|container|component|sequence|other|none\",\n"
    "  \"instructions\": \"string\",\n"
    "  \"requires_regeneration\": true|false,\n"
    "  \"plan\": [\n"
    "    {\"tool\": \"tool_name\", \"arguments\": {}}\n"
    "  ]\n"
    "}\n"
    "Rules:\n"
    "- If explain: intent=explain and plan should call explain_architecture.\n"
    "- If the user provides a GitHub URL: intent=regenerate and plan should call ingest_github_repo, then generate_architecture_plan and generate_multiple_diagrams.\n"
    "- If the user asks to generate/create a SEQUENCE diagram or PLANTUML diagram or flow diagram, AND state.has_architecture_plan is true: intent=generate_sequence and plan=[{tool: 'generate_sequence_from_architecture', arguments: {}}].\n"
    "- If multiple diagrams are needed: use generate_multiple_diagrams and include diagram_types in tool arguments.\n"
    "- If a single diagram type is requested: use generate_diagram.\n"
    "- If diagram type change: intent=diagram_change and plan should call generate_diagram when needed.\n"
    "- If edit image/diagram: intent=edit_image and plan should call edit_diagram_ir when possible.\n"
    "- If regenerate: intent=regenerate and plan should call generate_architecture_plan then generate_multiple_diagrams.\n"
    "- If unclear: intent=clarify and plan should be empty.\n"
    "- If diagram_count is provided, do not exceed it.\n"
    "- Choose target_image_id as the most recent image unless the user references a specific version.\n"
    "- CRITICAL: When user says 'generate sequence diagram' or 'create plantuml' or similar, and has_architecture_plan=true, you MUST use generate_sequence_from_architecture tool!"
)


def _extract_json(text: str) -> Dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return {}
    raw = match.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.replace("“", "\"").replace("”", "\"").replace("’", "'")
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}


def _extract_diagram_count(message: str) -> int | None:
    match = re.search(r"\b(\d+)\s*(diagram|diagrams|diagram(s))\b", message.lower())
    if match:
        try:
            value = int(match.group(1))
            return value if value > 0 else None
        except ValueError:
            return None
    return None


def _safe_list(items: List[Dict[str, Any]], keys: List[str]) -> List[Dict[str, Any]]:
    cleaned = []
    for item in items:
        cleaned.append({k: item.get(k) for k in keys})
    return cleaned


class ConversationPlannerAgent:
    """LLM-powered planner for conversation routing."""

    def plan(self, message: str, state: Dict[str, Any], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not settings.openai_api_key:
            return {
                "intent": "clarify",
                "diagram_count": _extract_diagram_count(message),
                "diagrams": [],
                "target_image_id": None,
                "target_diagram_type": "none",
                "instructions": "Missing OPENAI_API_KEY.",
                "requires_regeneration": False,
                "plan": [],
            }

        client = OpenAI(api_key=settings.openai_api_key)

        prompt = {
            "message": message,
            "tools": tools,
            "state": {
                "active_image_id": state.get("active_image_id"),
                "diagram_types": state.get("diagram_types", []),
                "images": _safe_list(state.get("images", []), ["id", "version", "reason"]),
                "history": state.get("history", []),
                "github_url": state.get("github_url"),
                "has_architecture_plan": bool(state.get("architecture_plan")),
                "input_text": state.get("input_text"),
            },
            "requested_diagram_count": _extract_diagram_count(message),
        }

        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM},
                {"role": "user", "content": json.dumps(prompt)},
            ],
            temperature=0.2,
        )

        raw = response.choices[0].message.content or "{}"
        data = _extract_json(raw)

        return {
            "intent": data.get("intent", "clarify"),
            "diagram_count": data.get("diagram_count"),
            "diagrams": data.get("diagrams", []),
            "target_image_id": data.get("target_image_id"),
            "target_diagram_type": data.get("target_diagram_type", "none"),
            "instructions": data.get("instructions", message),
            "requires_regeneration": bool(data.get("requires_regeneration", False)),
            "plan": data.get("plan", []),
        }
