"""Visual Agent (SDXL) using ADK BaseAgent."""
from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict

from google.adk.agents.base_agent import BaseAgent, BaseAgentState
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai import types

from src.models.architecture_plan import ArchitecturePlan
from src.tools.image_versioning import add_version
from src.tools.sdxl_renderer import run_sdxl


class VisualState(BaseAgentState):
    sdxl_prompt: str = ""
    image_file: str | None = None
    error: str | None = None


def _text_content(text: str) -> types.Content:
    return types.Content(parts=[types.Part(text=text)])


class VisualAgent(BaseAgent):
    """Generate SDXL prompt and image from ArchitecturePlan."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        plan_state = ctx.agent_states.get("architect", {}).get("architecture_plan")
        if not plan_state:
            raise ValueError("ArchitecturePlan not found in context")
        plan = ArchitecturePlan.model_validate(plan_state)
        prompt = build_visual_prompt(plan)
        image_file = None
        error = None
        try:
            image_file = run_sdxl(prompt, f"{ctx.session.id}_sdxl")
        except Exception as exc:
            error = str(exc)

        if image_file:
            add_version(ctx.session.id, image_file)

        state = VisualState(sdxl_prompt=prompt, image_file=image_file, error=error)
        ctx.set_agent_state(self.name, agent_state=state)
        event = Event(
            author=self.name,
            content=_text_content(json.dumps(state.model_dump(), indent=2)),
            actions=EventActions(state_delta={"visual": state.model_dump()}),
        )
        yield event


def build_visual_prompt(plan: ArchitecturePlan) -> str:
    zones = plan.zones
    relationships = [
        f"{rel.from_} -> {rel.to} ({rel.type}): {rel.description}"
        for rel in plan.relationships
    ]
    return (
        f"Create a clean software architecture diagram for '{plan.system_name}'. "
        f"Layout: {plan.visual_hints.layout}. "
        "Use a white or light background with a minimal, flat, professional style. "
        f"Group by zones: clients={zones.clients}, edge={zones.edge}, "
        f"core_services={zones.core_services}, external_services={zones.external_services}, "
        f"data_stores={zones.data_stores}. "
        "Show arrows for these relationships: "
        + "; ".join(relationships)
        + ". Do NOT add or remove components. Emphasize readability and spacing."
    )
