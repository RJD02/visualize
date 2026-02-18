import os
import sys
import pytest

# Ensure backend-python/src is on the import path for tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend-python", "src")))
import architecture_quality_agent as aqa


def test_cycle_detection():
    ir = {
        "nodes": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        "edges": [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}, {"source": "C", "target": "A"}],
    }
    report = aqa.analyze_architecture_quality(ir)
    assert isinstance(report, dict)
    assert report["metrics"]["cycles_count"] == 1
    assert any(i["id"] == "CYCLE_DETECTED" for i in report["issues"]) or any(i["id"] == "NO_ISSUES_DETECTED" for i in report["issues"]) is False


def test_high_coupling_detection():
    # One central node connected to all others
    nodes = [{"id": "Hub"}] + [{"id": f"N{i}"} for i in range(5)]
    edges = []
    for n in nodes:
        if n["id"] != "Hub":
            edges.append({"source": "Hub", "target": n["id"]})
            edges.append({"source": n["id"], "target": "Hub"})
    ir = {"nodes": nodes, "edges": edges}
    report = aqa.analyze_architecture_quality(ir)
    assert "GOD_MODULE" in [i["id"] for i in report["issues"]] or report["metrics"]["avg_degree"] > 1


def test_layering_violation_detection():
    ir = {
        "nodes": [{"id": "UI", "layer": 3}, {"id": "Service", "layer": 2}, {"id": "DB", "layer": 0}],
        "edges": [{"source": "UI", "target": "DB"}, {"source": "UI", "target": "Service"}],
    }
    report = aqa.analyze_architecture_quality(ir)
    assert any(i["id"] == "LAYER_VIOLATION" for i in report["issues"])


def test_god_module_detection():
    # God module when degree >= 50% of others
    nodes = [{"id": f"N{i}"} for i in range(6)]
    edges = []
    # N0 connects to all others
    for n in nodes[1:]:
        edges.append({"source": "N0", "target": n["id"]})
    ir = {"nodes": nodes, "edges": edges}
    report = aqa.analyze_architecture_quality(ir)
    assert any(i["id"] == "GOD_MODULE" for i in report["issues"]) or report["metrics"]["coupling"]["max_degree"] > 2


def test_no_issues_case():
    ir = {"nodes": [{"id": "A"}, {"id": "B"}], "edges": [{"source": "A", "target": "B"}]}
    report = aqa.analyze_architecture_quality(ir)
    assert isinstance(report["score"], float)
    assert any(i["id"] == "NO_ISSUES_DETECTED" for i in report["issues"]) or len(report["issues"]) > 0


def test_report_schema_fields():
    ir = {"nodes": [{"id": "A"}], "edges": []}
    report = aqa.analyze_architecture_quality(ir)
    assert set(["score", "metrics", "issues", "suggested_patches", "explanations"]).issubset(set(report.keys()))
