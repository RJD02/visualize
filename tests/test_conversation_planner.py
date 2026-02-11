from src.agents.conversation_planner_agent import (
    ConversationPlannerAgent,
    LATEST_IMAGE_PLACEHOLDER,
)


def test_planner_appends_style_step_for_generation_requests():
    planner = ConversationPlannerAgent()
    state = {
        "architecture_plan": None,
        "diagram_types": [],
        "images": [],
        "history": [],
        "github_url": None,
        "has_architecture_plan": False,
        "input_text": "sample",
    }
    plan = planner.plan(
        "Please generate a diagram with vibrant colours for the system",
        state,
        tools=[],
    )
    style_steps = [step for step in plan.get("plan", []) if step.get("tool") == "styling.apply_post_svg"]
    assert style_steps, "Planner should append a styling step"
    assert (
        style_steps[-1]["arguments"].get("diagramId") == LATEST_IMAGE_PLACEHOLDER
    ), "Styling step should target the latest generated diagram"
