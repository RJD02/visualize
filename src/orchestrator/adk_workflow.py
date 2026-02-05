"""ADK workflow orchestration using runtime APIs."""
from __future__ import annotations

from typing import Dict, List, Optional

from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.run_config import RunConfig
from google.adk.runners import InMemoryRunner
from google.genai import types

from src.agents.architect_agent import ArchitectAgent
from src.agents.diagram_agent import DiagramAgent
from src.agents.evaluator_agent import EvaluatorAgent
from src.agents.image_edit_agent import ImageEditAgent
from src.agents.visual_agent import VisualAgent
from src.tools.image_versioning import load_versions
from src.tools.text_extractor import extract_text


class ADKWorkflow:
    """Orchestrate the agent pipeline using ADK runtime APIs."""

    def _build_generate_agent(self) -> SequentialAgent:
        architect = ArchitectAgent(name="architect", description="Analyze architecture")
        diagram = DiagramAgent(name="diagram", description="Generate PlantUML")
        visual = VisualAgent(name="visual", description="Generate SDXL image")
        evaluator = EvaluatorAgent(name="evaluator", description="Evaluate outputs")
        return SequentialAgent(name="workflow", sub_agents=[architect, diagram, visual, evaluator])

    def _build_edit_agent(self) -> SequentialAgent:
        editor = ImageEditAgent(name="image_edit", description="Edit SDXL image")
        return SequentialAgent(name="edit_workflow", sub_agents=[editor])

    def _run_agent(self, agent: SequentialAgent, input_text: str, session_id: str) -> Dict[str, object]:
        runner = InMemoryRunner(agent=agent, app_name="archviz-adk")
        runner.auto_create_session = True
        content = types.Content(parts=[types.Part(text=input_text)])
        events = runner.run(
            user_id="user",
            session_id=session_id,
            new_message=content,
            run_config=RunConfig(),
        )
        state: Dict[str, object] = {}
        for event in events:
            if event.actions and event.actions.state_delta:
                state.update(event.actions.state_delta)
        return state

    def run(self, files: Optional[List[str]], text: Optional[str], output_name: str) -> Dict[str, object]:
        content = extract_text(files=files, text=text)
        state = self._run_agent(self._build_generate_agent(), content, output_name)
        return {
            "architecture_plan": state.get("architecture_plan"),
            "plantuml": {"files": state.get("plantuml_files", [])},
            "visual": state.get("visual", {}),
            "evaluation": state.get("evaluation", {"score": 0, "warnings": ["No evaluation"]}),
            "images": load_versions(output_name),
        }

    def run_edit(self, edit_text: str, output_name: str) -> Dict[str, object]:
        state = self._run_agent(self._build_edit_agent(), edit_text, output_name)
        return {
            "visual": state.get("visual", {}),
            "images": load_versions(output_name),
        }
