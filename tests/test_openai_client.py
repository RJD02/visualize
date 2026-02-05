from src.tools.schema_validator import validate_architecture_plan


def test_validate_architecture_plan():
    data = {
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
    plan = validate_architecture_plan(data)
    assert plan.system_name == "Test"
