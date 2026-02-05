"""Evaluator Agent (quality gate) using ADK BaseAgent."""
from __future__ import annotations

import json
from typing import AsyncGenerator, List

from google.adk.agents.base_agent import BaseAgent, BaseAgentState
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai import types

from src.models.architecture_plan import ArchitecturePlan


class EvaluationState(BaseAgentState):
    score: int = 100
    warnings: List[str] = []


def _text_content(text: str) -> types.Content:
    return types.Content(parts=[types.Part(text=text)])


class EvaluatorAgent(BaseAgent):
    """Validate ArchitecturePlan and outputs with basic heuristics."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        plan_state = ctx.agent_states.get("architect", {}).get("architecture_plan")
        if not plan_state:
            raise ValueError("ArchitecturePlan not found in context")
        plan = ArchitecturePlan.model_validate(plan_state)

        warnings: List[str] = []
        score = 100

        for rel in plan.relationships:
            if rel.from_.lower().startswith("class") or rel.to.lower().startswith("class"):
                warnings.append("Class-level artifact detected in relationships.")
                score -= 10

        if not plan.diagram_views:
            warnings.append("No diagram views specified.")
            score -= 10

        if not plan.zones.core_services:
            warnings.append("No core services listed.")
            score -= 5

        state = EvaluationState(score=max(score, 0), warnings=warnings)
        ctx.set_agent_state(self.name, agent_state=state)
        event = Event(
            author=self.name,
            content=_text_content(json.dumps(state.model_dump(), indent=2)),
            actions=EventActions(state_delta={"evaluation": state.model_dump()}),
        )
        yield event
