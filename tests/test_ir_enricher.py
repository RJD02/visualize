from src.tools.ir_enricher import enrich_ir, validate_enriched_ir


def _sample_ir() -> dict:
    return {
        "system_name": "Job Portal",
        "diagram_type": "system_context",
        "diagram_views": ["system_context", "container"],
        "visual_hints": {"layout": "left-to-right"},
        "zones": {
            "clients": ["Web Browser", "Mobile App"],
            "edge": ["API Gateway"],
            "core_services": ["User Service", "Job Service"],
            "external_services": ["Email Service"],
            "data_stores": ["PostgreSQL DB"],
        },
        "relationships": [
            {"from": "Web Browser", "to": "API Gateway", "type": "sync", "description": "User submits"},
            {"from": "API Gateway", "to": "User Service", "type": "sync", "description": "Forward call"},
            {"from": "User Service", "to": "PostgreSQL DB", "type": "data"},
        ],
        "aesthetic_intent": {
            "globalIntent": {"mood": "formal", "density": "compact"},
            "metadata": {"userPalette": ["#123", "rgb(16,32,48)"]},
        },
    }


def test_enrich_ir_generates_enriched_structure():
    enriched = enrich_ir(_sample_ir())

    assert enriched["diagram_type"] == "system_context"
    assert enriched["layout"] == "left-right"
    assert enriched["nodes"], "expected nodes to be populated"
    assert enriched["edges"], "expected edges to be populated"

    palette = enriched["globalIntent"]["palette"]
    assert palette[0] == "#112233"
    assert palette[1] == "#102030"

    node_ids = {node["node_id"] for node in enriched["nodes"]}
    assert "api_gateway" in node_ids

    errors = validate_enriched_ir(enriched)
    assert errors == []


def test_enrich_ir_infers_missing_nodes_and_records_warning():
    payload = _sample_ir()
    payload["zones"]["core_services"] = []
    payload["relationships"].append({"from": "Queue Worker", "to": "Email Service", "type": "async"})

    enriched = enrich_ir(payload)

    labels = {node["label"] for node in enriched["nodes"]}
    assert "Queue Worker" in labels

    warnings = [entry for entry in enriched["metadata"]["validation"] if entry["severity"] == "warning"]
    assert warnings, "expected at least one warning for inferred node"


def test_validate_enriched_ir_reports_schema_errors():
    invalid = {"layout": "top-down"}
    errors = validate_enriched_ir(invalid)
    assert errors
    assert any("diagram_type" in err for err in errors)
