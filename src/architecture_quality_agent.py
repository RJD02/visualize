"""Architecture Quality Analysis Agent

Implements deterministic structural metrics on an IR and returns a
structured architecture quality report suitable for LLM-assisted
interpretation and UI integration.

Contract:
  Input: { "ir": {...}, "context": "optional" }
  Output: { "score": number, "issues": [...], "suggested_patches": [...], "explanations": [...] }

This module is purposely self-contained and avoids calling external LLMs
directly; it prepares the structured prompt and falls back to deterministic
explanations when an LLM is unavailable.
"""
from typing import Any, Dict, List, Tuple
import math
import networkx as nx


def _build_graph(ir: Dict[str, Any]) -> Tuple[nx.DiGraph, Dict[str, Dict[str, Any]]]:
    g = nx.DiGraph()
    nodes = {}
    for n in ir.get("nodes", []):
        nid = n.get("id") or n.get("name")
        if nid is None:
            continue
        nodes[nid] = n
        g.add_node(nid, **n)

    for e in ir.get("edges", []):
        s = e.get("source")
        t = e.get("target")
        if s is None or t is None:
            continue
        g.add_edge(s, t, **e)

    return g, nodes


def _detect_cycles(g: nx.DiGraph) -> List[List[str]]:
    return [list(cycle) for cycle in nx.simple_cycles(g)]


def _coupling_metrics(g: nx.DiGraph) -> Dict[str, Any]:
    deg_in = dict(g.in_degree())
    deg_out = dict(g.out_degree())
    degrees = {n: deg_in.get(n, 0) + deg_out.get(n, 0) for n in g.nodes()}
    n = max(1, g.number_of_nodes())
    avg_degree = sum(degrees.values()) / n
    max_degree = max(degrees.values()) if degrees else 0
    max_degree_ratio = max_degree / max(1, (n - 1))
    return {
        "in_degree": deg_in,
        "out_degree": deg_out,
        "degree": degrees,
        "avg_degree": avg_degree,
        "max_degree": max_degree,
        "max_degree_ratio": max_degree_ratio,
    }


def _layering_violations(g: nx.DiGraph, nodes: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    violations = []
    for u, v, data in g.edges(data=True):
        lu = nodes.get(u, {}).get("layer")
        lv = nodes.get(v, {}).get("layer")
        if lu is None or lv is None:
            continue
        # Define layering numbers where larger means higher-level.
        # Violation if the edge skips >1 layer (accessing far lower layer directly).
        if (lu - lv) > 1:
            violations.append({"source": u, "target": v, "source_layer": lu, "target_layer": lv})
    return violations


def _centrality_risk(g: nx.DiGraph) -> Dict[str, Any]:
    n = max(1, g.number_of_nodes())
    deg = dict(g.degree())
    sorted_nodes = sorted(deg.items(), key=lambda kv: kv[1], reverse=True)
    top_node, top_deg = sorted_nodes[0] if sorted_nodes else (None, 0)
    god_threshold = 0.5 * max(1, n - 1)
    is_god = top_deg >= god_threshold
    # betweenness centrality normalized
    bc = nx.betweenness_centrality(g) if n > 1 else {k: 0.0 for k in g.nodes()}
    return {"top_node": top_node, "top_degree": top_deg, "is_god_module": is_god, "betweenness": bc}


def _cohesion_signal(ir: Dict[str, Any], nodes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    # Cohesion requires internal structure. Look for `members` or `components` inside node attributes.
    cohesion = {}
    for nid, meta in nodes.items():
        members = meta.get("members") or meta.get("components")
        if isinstance(members, list) and len(members) > 1:
            # naive heuristic: if members exist but no edges between them are present in IR, low cohesion
            cohesion[nid] = {"member_count": len(members), "cohesion_estimate": "unknown"}
        else:
            cohesion[nid] = {"member_count": len(members) if isinstance(members, list) else 0, "cohesion_estimate": "unknown"}
    return cohesion


def _score_from_metrics(metrics: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
    # Deterministic explainable scoring: 0-100
    # Components: cycles (bad), avg_degree (coupling), max_degree_ratio (centrality), layering_violations
    cycles = metrics.get("cycles_count", 0)
    avg_deg = metrics.get("avg_degree", 0.0)
    max_deg_ratio = metrics.get("max_degree_ratio", 0.0)
    layering = metrics.get("layering_violations_count", 0)

    # Normalize components to 0..1 where 1 is worst
    # cycles: more cycles worse, normalize by (cycles / (n or 1)) capped
    n = max(1, metrics.get("node_count", 1))
    cycles_norm = min(1.0, cycles / max(1, n))
    # avg_deg normalized by (n-1)
    avg_deg_norm = min(1.0, avg_deg / max(1, n - 1))
    max_deg_norm = min(1.0, max_deg_ratio)
    layering_norm = min(1.0, layering / max(1, n))

    # Weights
    w_cycles = 0.35
    w_coupling = 0.25
    w_central = 0.25
    w_layer = 0.15

    badness = (w_cycles * cycles_norm) + (w_coupling * avg_deg_norm) + (w_central * max_deg_norm) + (w_layer * layering_norm)
    score = max(0.0, 100.0 * (1.0 - badness))
    breakdown = {
        "cycles_norm": cycles_norm,
        "avg_deg_norm": avg_deg_norm,
        "max_deg_norm": max_deg_norm,
        "layering_norm": layering_norm,
        "badness": badness,
    }
    return score, breakdown


def _generate_issues(metrics: Dict[str, Any], central: Dict[str, Any], layering_violations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    issues = []
    # cycles
    if metrics.get("cycles_count", 0) > 0:
        issues.append({
            "id": "CYCLE_DETECTED",
            "description": f"Detected {metrics['cycles_count']} cycle(s) in the dependency graph.",
            "severity": "high",
            "metrics": {"cycles": metrics.get("cycles_list", [])},
            "confidence": [0.9, 0.99],
        })

    # God module
    if central.get("is_god_module"):
        issues.append({
            "id": "GOD_MODULE",
            "description": f"Node '{central['top_node']}' has exceptionally high degree ({central['top_degree']}).",
            "severity": "high",
            "metrics": {"top_node": central["top_node"], "top_degree": central["top_degree"]},
            "confidence": [0.8, 0.95],
        })

    # coupling
    if metrics.get("avg_degree", 0) > max(1.0, metrics.get("node_count", 1) * 0.8):
        issues.append({
            "id": "HIGH_COUPLING",
            "description": "Architecture shows high average coupling between modules.",
            "severity": "medium",
            "metrics": {"avg_degree": metrics.get("avg_degree")},
            "confidence": [0.6, 0.9],
        })

    # layering violations
    for v in layering_violations:
        issues.append({
            "id": "LAYER_VIOLATION",
            "description": f"Layering violation: {v['source']} (layer {v['source_layer']}) -> {v['target']} (layer {v['target_layer']}).",
            "severity": "medium",
            "metrics": v,
            "confidence": [0.7, 0.9],
        })

    if not issues:
        issues.append({
            "id": "NO_ISSUES_DETECTED",
            "description": "No deterministic issues detected.",
            "severity": "low",
            "metrics": {},
            "confidence": [0.8, 0.99],
        })

    return issues


def _suggest_patches(issues: List[Dict[str, Any]], g: nx.DiGraph) -> List[Dict[str, Any]]:
    patches = []
    for issue in issues:
        iid = issue["id"]
        if iid == "CYCLE_DETECTED":
            # suggest breaking a cycle by removing one edge per cycle
            cycles = issue["metrics"].get("cycles", [])
            for cycle in cycles:
                if len(cycle) >= 2:
                    a = cycle[0]
                    b = cycle[1]
                    patches.append({
                        "issue_id": iid,
                        "op": "remove_edge",
                        "source": a,
                        "target": b,
                        "explanation": "Break the cycle by removing dependency edge.",
                    })

        elif iid == "GOD_MODULE":
            node = issue["metrics"].get("top_node") or issue["metrics"].get("top_node")
            if node:
                patches.append({
                    "issue_id": iid,
                    "op": "extract_interface",
                    "node": node,
                    "new_node": f"{node}_interface",
                    "explanation": "Introduce an interface/adapter to split responsibilities and reduce direct coupling.",
                })

        elif iid == "LAYER_VIOLATION":
            src = issue["metrics"].get("source")
            tgt = issue["metrics"].get("target")
            if src and tgt:
                patches.append({
                    "issue_id": iid,
                    "op": "add_abstraction",
                    "between": [src, tgt],
                    "explanation": "Add an intermediate service/abstraction to respect layering.",
                })

        elif iid == "HIGH_COUPLING":
            patches.append({
                "issue_id": iid,
                "op": "add_interface_nodes",
                "explanation": "Identify high-degree modules and introduce interfaces or facades to reduce coupling.",
            })

        # NO_ISSUES_DETECTED or unknown -> no-op suggestion
    return patches


def prepare_llm_prompt(ir: Dict[str, Any], metrics: Dict[str, Any], issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Prepare a structured prompt payload for an LLM to interpret metrics.

    The LLM must not invent new metrics. Use this payload when integrating an LLM.
    """
    return {
        "ir_summary": {
            "node_count": metrics.get("node_count"),
            "edge_count": metrics.get("edge_count"),
        },
        "metrics": metrics,
        "issues": issues,
        "goals": [
            "Explain what each potential architecture concern means.",
            "Explain how suggested patches relate to improving quality.",
            "Avoid inventing new metrics or unsupported suggestions.",
        ],
    }


def generate_explanations_with_llm(prompt_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Placeholder: in production this should call a safe LLM endpoint with the structured prompt.
    # To avoid hallucinations we provide conservative deterministic explanations here.
    explanations = []
    for issue in prompt_payload.get("issues", []):
        explanations.append({
            "issue_id": issue["id"],
            "explanation": issue.get("description") + "\n\n(Interpretation: deterministic metrics were used; no extra claims.)",
            "confidence": issue.get("confidence", [0.5, 0.9]),
        })
    return explanations


def analyze_architecture_quality(ir: Dict[str, Any], context: str = None) -> Dict[str, Any]:
    g, nodes = _build_graph(ir)
    node_count = g.number_of_nodes()
    edge_count = g.number_of_edges()

    cycles = _detect_cycles(g)
    coupling = _coupling_metrics(g)
    layering_viol = _layering_violations(g, nodes)
    central = _centrality_risk(g)
    cohesion = _cohesion_signal(ir, nodes)

    metrics = {
        "node_count": node_count,
        "edge_count": edge_count,
        "cycles_count": len(cycles),
        "cycles_list": cycles,
        "avg_degree": coupling.get("avg_degree"),
        "max_degree_ratio": coupling.get("max_degree_ratio"),
        "layering_violations_count": len(layering_viol),
        "coupling": coupling,
        "cohesion": cohesion,
    }

    score, breakdown = _score_from_metrics(metrics)
    metrics["score_breakdown"] = breakdown

    issues = _generate_issues(metrics, central, layering_viol)
    suggested_patches = _suggest_patches(issues, g)

    llm_prompt = prepare_llm_prompt(ir, metrics, issues)
    explanations = generate_explanations_with_llm(llm_prompt)

    report = {
        "score": round(score, 2),
        "metrics": metrics,
        "issues": issues,
        "suggested_patches": suggested_patches,
        "explanations": explanations,
        "confidence": [0.7, 0.99],
    }
    return report


if __name__ == "__main__":
    # simple local demo
    demo_ir = {
        "nodes": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        "edges": [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}, {"source": "C", "target": "A"}],
    }
    import json

    print(json.dumps(analyze_architecture_quality(demo_ir), indent=2))
