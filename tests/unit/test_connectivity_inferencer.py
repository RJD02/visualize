"""Unit tests for IR connectivity inference — STORY-DIAGRAM-COHESION-01.

Tests drive _IREnricher directly to verify zone-cascade, tech-dependency,
and completion-guard rules produce connected, deterministic diagrams.

Acceptance criteria:
  isolated_nodes / total_nodes <= 0.15
  total_edges >= max(total_nodes - 1, 10)
  inferred edges are dashed and explainable
  same input yields same output
"""
from __future__ import annotations

import pytest

from src.tools.ir_enricher import _IREnricher


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_ir(zones: dict, relationships: list | None = None) -> dict:
    """Build a minimal IR input dict for _IREnricher."""
    return {
        "system_name": "Test System",
        "diagram_views": ["component"],
        "zones": zones,
        "relationships": relationships or [],
    }


def _nodes_in_zone(enricher: _IREnricher, zone: str) -> list[dict]:
    return [n for n in enricher.nodes if n.get("zone") == zone]


def _has_edge(enricher: _IREnricher, from_zone: str, to_zone: str) -> bool:
    """Return True if any edge connects a node in from_zone to a node in to_zone."""
    from_ids = {n["node_id"] for n in _nodes_in_zone(enricher, from_zone)}
    to_ids = {n["node_id"] for n in _nodes_in_zone(enricher, to_zone)}
    return any(
        e["from_id"] in from_ids and e["to_id"] in to_ids
        for e in enricher.edges
    )


def _isolated_count(enricher: _IREnricher) -> int:
    with_edges = set()
    for e in enricher.edges:
        with_edges.add(e["from_id"])
        with_edges.add(e["to_id"])
    return sum(1 for n in enricher.nodes if n["node_id"] not in with_edges)


# ─── Test 1 ───────────────────────────────────────────────────────────────────

def test_zone_cascade_adds_edges_when_none_exist():
    """Rule 1: each adjacent zone pair receives a bridging edge when no explicit edge exists."""
    zones = {
        "clients": ["Web App"],
        "edge": ["API Gateway"],
        "core_services": ["Auth Service"],
        "data_stores": ["PostgreSQL"],
    }
    enricher = _IREnricher(_make_ir(zones))
    enricher.build()

    for from_zone, to_zone in [
        ("clients", "edge"),
        ("edge", "core_services"),
        ("core_services", "data_stores"),
    ]:
        assert _has_edge(enricher, from_zone, to_zone), (
            f"No edge found from '{from_zone}' to '{to_zone}' after zone cascade rule"
        )


# ─── Test 2 ───────────────────────────────────────────────────────────────────

def test_isolated_ratio_below_threshold():
    """9 nodes, 0 explicit relationships → isolated / total <= 0.15."""
    zones = {
        "clients": ["Browser", "Mobile App"],
        "edge": ["API Gateway", "Load Balancer"],
        "core_services": ["Auth", "Catalog", "Orders"],
        "data_stores": ["Postgres", "Redis", "MongoDB"],
    }
    enricher = _IREnricher(_make_ir(zones, relationships=[]))
    enricher.build()

    total = len(enricher.nodes)
    isolated = _isolated_count(enricher)
    assert total == 10, f"Expected 10 nodes (2+2+3+3), got {total}"
    assert isolated / total <= 0.15, (
        f"isolated ratio {isolated}/{total} = {isolated/total:.2f} exceeds 0.15"
    )


# ─── Test 3 ───────────────────────────────────────────────────────────────────

def test_minimum_edge_count_met():
    """12 nodes, 0 explicit relationships → edge count >= max(total_nodes - 1, 10)."""
    zones = {
        "clients": ["Browser", "Mobile"],
        "edge": ["API Gateway", "Load Balancer"],
        "core_services": ["Auth", "Orders", "Catalog"],
        "external_services": ["Payment", "Email"],
        "data_stores": ["Postgres", "Redis", "Mongo"],
    }
    enricher = _IREnricher(_make_ir(zones, relationships=[]))
    enricher.build()

    total = len(enricher.nodes)
    assert total == 12
    min_expected = max(total - 1, 10)
    assert len(enricher.edges) >= min_expected, (
        f"edge count {len(enricher.edges)} < max({total - 1}, 10) = {min_expected}"
    )


# ─── Test 4 ───────────────────────────────────────────────────────────────────

def test_determinism_same_input_same_output():
    """Two independent _IREnricher runs on the same IR produce identical edge lists."""
    zones = {
        "clients": ["Browser"],
        "edge": ["API Gateway"],
        "core_services": ["Auth Service", "Order Service"],
        "data_stores": ["PostgreSQL", "Redis"],
    }
    ir = _make_ir(zones)

    enricher1 = _IREnricher(ir)
    result1 = enricher1.build()

    enricher2 = _IREnricher(ir)
    result2 = enricher2.build()

    pairs1 = [(e["from_id"], e["to_id"]) for e in result1["edges"]]
    pairs2 = [(e["from_id"], e["to_id"]) for e in result2["edges"]]
    assert pairs1 == pairs2, "Edge order differs between identical runs — non-determinism detected"


# ─── Test 5 ───────────────────────────────────────────────────────────────────

def test_no_duplicate_edge_when_explicit_exists():
    """If an explicit edge already bridges clients→edge, no second inferred edge is added."""
    zones = {
        "clients": ["Browser"],
        "edge": ["API Gateway"],
        "core_services": ["Auth Service"],
    }
    relationships = [
        {"from": "Browser", "to": "API Gateway", "type": "sync", "description": "explicit"},
    ]
    enricher = _IREnricher(_make_ir(zones, relationships))
    enricher.build()

    client_ids = {n["node_id"] for n in _nodes_in_zone(enricher, "clients")}
    edge_zone_ids = {n["node_id"] for n in _nodes_in_zone(enricher, "edge")}
    connecting = [
        e for e in enricher.edges
        if e["from_id"] in client_ids and e["to_id"] in edge_zone_ids
    ]
    assert len(connecting) == 1, (
        f"Expected exactly 1 edge clients→edge, found {len(connecting)}: {connecting}"
    )


# ─── Test 6 ───────────────────────────────────────────────────────────────────

def test_explainability_record_structure():
    """Each inferred edge must have rule, reason, and confidence in inference_log."""
    zones = {
        "clients": ["Browser"],
        "edge": ["API Gateway"],
        "core_services": ["Auth Service"],
        "data_stores": ["PostgreSQL"],
    }
    enricher = _IREnricher(_make_ir(zones))
    enricher.build()

    assert enricher.inference_log, "inference_log must not be empty when edges are inferred"
    valid_confidences = {0.3, 0.5, 0.7}
    for record in enricher.inference_log:
        assert "rule" in record, f"inference_log entry missing 'rule': {record}"
        assert "reason" in record, f"inference_log entry missing 'reason': {record}"
        assert "confidence" in record, f"inference_log entry missing 'confidence': {record}"
        assert record["confidence"] in valid_confidences, (
            f"Unexpected confidence {record['confidence']} — expected one of {valid_confidences}"
        )


# ─── Test 7 ───────────────────────────────────────────────────────────────────

def test_tech_dependency_kafka_to_processor():
    """Rule 2: a Kafka node and an Event Processor node produce an inferred async edge."""
    zones = {
        "edge": ["Kafka"],
        "core_services": ["Event Processor", "Order Service"],
    }
    enricher = _IREnricher(_make_ir(zones))
    enricher.build()

    kafka_node = next((n for n in enricher.nodes if "kafka" in n["label"].lower()), None)
    processor_node = next(
        (n for n in enricher.nodes if "processor" in n["label"].lower()), None
    )
    assert kafka_node, "Kafka node not found"
    assert processor_node, "Event Processor node not found"

    has_edge = any(
        e["from_id"] == kafka_node["node_id"] and e["to_id"] == processor_node["node_id"]
        for e in enricher.edges
    )
    assert has_edge, (
        f"No async edge inferred from Kafka ({kafka_node['node_id']}) "
        f"to Event Processor ({processor_node['node_id']})"
    )


# ─── Test 8 ───────────────────────────────────────────────────────────────────

def test_completion_guard_removes_all_isolated():
    """Rule 3: a node with no cascade/tech neighbours is connected by the completion guard."""
    # Browser is in 'clients' but no 'edge' zone exists, so cascade pair clients→edge is skipped.
    # core_services→data_stores cascade connects Auth and PostgreSQL.
    # Rule 3 must then connect Browser to an already-connected node.
    zones = {
        "clients": ["Browser"],
        "core_services": ["Auth Service"],
        "data_stores": ["PostgreSQL"],
    }
    enricher = _IREnricher(_make_ir(zones, relationships=[]))
    enricher.build()

    isolated = _isolated_count(enricher)
    assert isolated == 0, (
        f"Completion guard left {isolated} isolated node(s): "
        f"{[n['label'] for n in enricher.nodes if n['node_id'] not in {e['from_id'] for e in enricher.edges} | {e['to_id'] for e in enricher.edges}]}"
    )
    # The guard edge must be in the inference_log with rule='completion_guard'
    guard_entries = [r for r in enricher.inference_log if r.get("rule") == "completion_guard"]
    assert guard_entries, "No completion_guard entry in inference_log"
    for entry in guard_entries:
        assert entry["confidence"] == 0.3, (
            f"completion_guard confidence must be 0.3, got {entry['confidence']}"
        )
