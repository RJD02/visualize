"""Diagram Agent (deterministic PlantUML) using ADK BaseAgent."""
from __future__ import annotations

import json
from typing import AsyncGenerator, Dict, List

from google.adk.agents.base_agent import BaseAgent, BaseAgentState
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai import types

from src.models.architecture_plan import ArchitecturePlan, Relationship
from src.tools.ir_enricher import _IREnricher
from src.tools.plantuml_renderer import generate_plantuml_from_plan, render_diagrams


class DiagramState(BaseAgentState):
    plantuml_files: list[str] = []


def _text_content(text: str) -> types.Content:
    return types.Content(parts=[types.Part(text=text)])


def _merge_inferred_edges(plan: ArchitecturePlan, enricher: _IREnricher) -> ArchitecturePlan:
    """Append inferred edges from enricher.inference_log to plan.relationships.

    Converts enricher node IDs back to labels using the enricher's node list and
    deduplicates against existing relationships before appending.
    """
    if not enricher.inference_log:
        return plan

    id_to_label: Dict[str, str] = {
        node["node_id"]: node["label"]  # type: ignore[index]
        for node in enricher.nodes
    }
    existing_pairs = {(rel.from_, rel.to) for rel in plan.relationships}
    new_rels: List[Relationship] = []

    for entry in enricher.inference_log:
        from_label = id_to_label.get(str(entry["from_id"]), str(entry["from_id"]))
        to_label = id_to_label.get(str(entry["to_id"]), str(entry["to_id"]))
        if (from_label, to_label) in existing_pairs:
            continue
        new_rels.append(
            Relationship.model_validate({
                "from": from_label,
                "to": to_label,
                "type": entry.get("rel_type", "async"),
                "description": str(entry["reason"]),
            })
        )
        existing_pairs.add((from_label, to_label))

    if not new_rels:
        return plan
    return plan.model_copy(update={"relationships": list(plan.relationships) + new_rels})


class DiagramAgent(BaseAgent):
    """Convert ArchitecturePlan to PlantUML and render diagrams."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        plan_state = ctx.agent_states.get("architect", {}).get("architecture_plan")
        if not plan_state:
            raise ValueError("ArchitecturePlan not found in context")
        plan = ArchitecturePlan.model_validate(plan_state)

        # Enrich IR with connectivity inference before rendering
        enricher = _IREnricher(plan.model_dump(by_alias=True))
        enricher.build()
        plan = _merge_inferred_edges(plan, enricher)

        diagrams = generate_plantuml_from_plan(plan)
        files = render_diagrams(diagrams, ctx.session.id)

        ctx.set_agent_state(self.name, agent_state=DiagramState(plantuml_files=files))
        event = Event(
            author=self.name,
            content=_text_content(json.dumps({"plantuml_files": files}, indent=2)),
            actions=EventActions(state_delta={"plantuml_files": files}),
        )
        yield event
