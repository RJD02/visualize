from src.models.architecture_plan import ArchitecturePlan
from src.tools.plantuml_renderer import generate_plantuml_from_plan


def test_generate_component_diagram():
    plan = ArchitecturePlan.model_validate(
        {
            "system_name": "Test",
            "diagram_views": ["component"],
            "zones": {
                "clients": ["Client"],
                "edge": [],
                "core_services": ["Service"],
                "external_services": [],
                "data_stores": [],
            },
            "relationships": [
                {"from": "Client", "to": "Service", "type": "sync", "description": "calls"}
            ],
            "visual_hints": {"layout": "left-to-right", "group_by_zone": True, "external_dashed": True},
        }
    )
    diagrams = generate_plantuml_from_plan(plan)
    assert diagrams
    assert "@startuml" in diagrams[0]["plantuml"]
    assert "component \"Client\"" in diagrams[0]["plantuml"]
    assert "Client --> Service" in diagrams[0]["plantuml"]
