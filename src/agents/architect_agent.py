"""Architect Agent (ADK BaseAgent)."""
from __future__ import annotations

import json
import re
from typing import Any, AsyncGenerator, Dict

from google.adk.agents.base_agent import BaseAgent, BaseAgentState
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai import types

from src.models.architecture_plan import ArchitecturePlan
from src.tools.file_storage import save_json
from src.tools.schema_validator import validate_architecture_plan
from src.utils.config import settings
from src.utils.openai_client import get_openai_client


ARCHITECT_INSTRUCTION = (
    "You are a diagram planning agent. "
    "Analyze the input and build a structured plan for diagrams. "
    "Think in responsibilities, boundaries, and data flow. "
    "If the input is a narrative/story/workflow, emphasize sequence/flow views and treat actors as clients. "
    "Do not describe classes or methods. "
    "Output ONLY valid JSON and match this exact schema:\n"
    "{\n"
    "  \"system_name\": \"string\",\n"
    "  \"diagram_views\": [\"system_context\", \"container\", \"component\", \"sequence\", \"flow\"],\n"
    "  \"zones\": {\n"
    "    \"clients\": [],\n"
    "    \"edge\": [],\n"
    "    \"core_services\": [],\n"
    "    \"external_services\": [],\n"
    "    \"data_stores\": []\n"
    "  },\n"
    "  \"relationships\": [\n"
    "    {\"from\": \"string\", \"to\": \"string\", \"type\": \"sync|async|data|auth\", \"description\": \"string\"}\n"
    "  ],\n"
    "  \"visual_hints\": {\n"
    "    \"layout\": \"left-to-right|top-down\",\n"
    "    \"group_by_zone\": true,\n"
    "    \"external_dashed\": true\n"
    "  },\n"
    "  \"diagram_kind\": \"architecture|sequence|flow|story|other\",\n"
    "  \"rendering_hints\": {\n"
    "    \"preferred_renderer\": \"auto|plantuml|mermaid|structurizr\",\n"
    "    \"confidence\": 0.0\n"
    "  },\n"
    "  \"narrative\": \"optional summary of story/flow if present\"\n"
    "}\n"
)


class ArchitectState(BaseAgentState):
    architecture_plan: Dict[str, Any] = {}


def _extract_json(text: str) -> Dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in model output")
    raw = match.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.replace("“", "\"").replace("”", "\"").replace("’", "'")
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            import ast

            pythonish = re.sub(r"(?<=:\s)(true|false|null)\b", lambda m: {"true": "True", "false": "False", "null": "None"}[m.group(1)], cleaned)
            return ast.literal_eval(pythonish)


def _build_context_block(context: Dict[str, Any] | None) -> str:
    if not context:
        return ""
    fields = []
    user_message = context.get("user_message")
    if user_message:
        fields.append(f"User request: {user_message}")
    source_repo = context.get("source_repo") or context.get("repo_url")
    if source_repo:
        fields.append(f"Source repo: {source_repo}")
    input_text = context.get("input_text")
    if input_text and input_text != user_message:
        fields.append(f"Original input: {input_text}")
    return "\n".join(fields)


def generate_architecture_plan_from_text(input_text: str, *, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set")
    client = get_openai_client()
    context_block = _build_context_block(context)
    prompt = f"Input:\n{input_text}"
    if context_block:
        prompt = f"{context_block}\n\n{prompt}"
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": ARCHITECT_INSTRUCTION},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    raw = response.choices[0].message.content or ""
    data = _extract_json(raw)
    if "ArchitecturePlan" in data:
        data = data["ArchitecturePlan"]
    plan = validate_architecture_plan(data)
    return plan.model_dump(by_alias=True)


def _content_text(content: types.Content | None) -> str:
    if not content or not content.parts:
        return ""
    return "\n".join([p.text for p in content.parts if p.text])


def _text_content(text: str) -> types.Content:
    return types.Content(parts=[types.Part(text=text)])


class ArchitectAgent(BaseAgent):
    """Reasoning agent that outputs ArchitecturePlan via ADK runtime."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        input_text = _content_text(ctx.user_content)
        plan = validate_architecture_plan(generate_architecture_plan_from_text(input_text))

        ctx.set_agent_state(self.name, agent_state=ArchitectState(architecture_plan=plan.model_dump(by_alias=True)))
        save_json(f"{ctx.session.id}_architecture_plan.json", plan.model_dump(by_alias=True))

        event = Event(
            author=self.name,
            content=_text_content(json.dumps(plan.model_dump(by_alias=True), indent=2)),
            actions=EventActions(state_delta={"architecture_plan": plan.model_dump(by_alias=True)}),
        )
        yield event
