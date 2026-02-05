"""Image Edit Agent (iterative SDXL edits) using ADK BaseAgent."""
from __future__ import annotations

import json
from typing import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent, BaseAgentState
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai import types

from src.models.architecture_plan import ArchitecturePlan
from src.tools.file_storage import load_json
from src.tools.file_storage import load_text
from pathlib import Path
import xml.etree.ElementTree as ET
from src.utils.config import settings
from src.tools.image_versioning import add_version
from src.tools.sdxl_renderer import run_sdxl_edit
from src.tools.schema_validator import validate_architecture_plan
from src.tools.text_extractor import extract_text
from src.utils.config import settings


class ImageEditState(BaseAgentState):
    prompt: str = ""
    image_file: str | None = None
    error: str | None = None


def _text_content(text: str) -> types.Content:
    return types.Content(parts=[types.Part(text=text)])


def _build_edit_prompt(plan: ArchitecturePlan, edit_instruction: str) -> str:
    components = (
        plan.zones.clients
        + plan.zones.edge
        + plan.zones.core_services
        + plan.zones.external_services
        + plan.zones.data_stores
    )
    component_list = ", ".join(components)
    return (
        "Render a clean software architecture diagram on a white background. "
        "Preserve all components and boundaries exactly as defined. "
        f"Components: {component_list}. "
        f"Layout hint: {plan.visual_hints.layout}. "
        "Do not add or remove components. "
        "Do not change system boundaries. "
        f"Edit request: {edit_instruction}"
    )


class ImageEditAgent(BaseAgent):
    """Iteratively edit the SDXL image while preserving architecture."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        edit_instruction = extract_text(text=_content_text(ctx.user_content))
        plan_state = ctx.agent_states.get("architect", {}).get("architecture_plan")
        if not plan_state:
            plan_state = load_json(f"{ctx.session.id}_architecture_plan.json")
        plan = validate_architecture_plan(plan_state)

        # Attempt to load the most recent SVG IR for this session (saved by renderer)
        svg_text = None
        try:
            out_dir = Path(settings.output_dir)
            pattern = f"{ctx.session.id}_*.svg"
            files = list(out_dir.glob(pattern))
            if files:
                latest = max(files, key=lambda p: p.stat().st_mtime)
                svg_text = load_text(latest.name)
        except Exception:
            svg_text = None

        # Extract IR metadata if available
        ir_metadata = None
        if svg_text:
            try:
                root = ET.fromstring(svg_text)
                for elem in root.iter():
                    if elem.tag.endswith("metadata"):
                        ir_metadata = elem.text
                        break
            except Exception:
                ir_metadata = None

        # Build prompt that references IR metadata so the LLM edits according to IR
        ir_block = f"IR metadata: {ir_metadata}\n" if ir_metadata else ""
        prompt = ir_block + _build_edit_prompt(plan, edit_instruction)
        image_file = None
        error = None
        try:
            image_file = run_sdxl_edit(prompt, f"{ctx.session.id}_sdxl_edit")
        except Exception as exc:
            error = str(exc)

        if image_file:
            add_version(ctx.session.id, image_file)

        state = ImageEditState(prompt=prompt, image_file=image_file, error=error)
        ctx.set_agent_state(self.name, agent_state=state)
        event = Event(
            author=self.name,
            content=_text_content(json.dumps(state.model_dump(), indent=2)),
            actions=EventActions(state_delta={"visual": state.model_dump()}),
        )
        yield event


def _content_text(content: types.Content | None) -> str:
    if not content or not content.parts:
        return ""
    return "\n".join([p.text for p in content.parts if p.text])
