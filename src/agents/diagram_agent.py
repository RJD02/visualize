"""Diagram Agent (deterministic PlantUML) using ADK BaseAgent."""
from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict

from google.adk.agents.base_agent import BaseAgent, BaseAgentState
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai import types

from src.models.architecture_plan import ArchitecturePlan
from src.tools.plantuml_renderer import generate_plantuml_from_plan, render_diagrams


class DiagramState(BaseAgentState):
    plantuml_files: list[str] = []


def _text_content(text: str) -> types.Content:
    return types.Content(parts=[types.Part(text=text)])


class DiagramAgent(BaseAgent):
    """Convert ArchitecturePlan to PlantUML and render diagrams."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        plan_state = ctx.agent_states.get("architect", {}).get("architecture_plan")
        if not plan_state:
            raise ValueError("ArchitecturePlan not found in context")
        plan = ArchitecturePlan.model_validate(plan_state)
        diagrams = generate_plantuml_from_plan(plan)
        files = render_diagrams(diagrams, ctx.session.id)

        ctx.set_agent_state(self.name, agent_state=DiagramState(plantuml_files=files))
        event = Event(
            author=self.name,
            content=_text_content(json.dumps({"plantuml_files": files}, indent=2)),
            actions=EventActions(state_delta={"plantuml_files": files}),
        )
        yield event
