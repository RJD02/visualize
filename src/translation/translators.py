"""Deterministic translators from Structural IR -> renderer inputs.

These translators produce plain-text inputs for the renderer layer.
No aesthetics are applied here.
"""
from __future__ import annotations

from typing import Dict
from src.ir.schemas import StructuralIR


def structural_to_mermaid(struct: StructuralIR) -> str:
    """Produce a Mermaid diagram from Structural IR.

    If the IR indicates a sequence diagram (via `diagram_kind` or node/edge hints),
    emit a `sequenceDiagram`. Otherwise emit a `flowchart LR` as before.
    """
    # Heuristics for sequence diagram:
    is_sequence = False
    if getattr(struct, "diagram_kind", None) == "sequence":
        is_sequence = True
    else:
        # if any node has type Actor or any edge has a non-empty label, prefer sequence
        for n in getattr(struct, "nodes", []) or []:
            if (n.get("type") or "").lower() == "actor":
                is_sequence = True
                break
        if not is_sequence:
            for e in getattr(struct, "edges", []) or []:
                if e.get("label"):
                    is_sequence = True
                    break

    if is_sequence:
        lines = ["sequenceDiagram"]
        # participants - preserve order in nodes if possible
        parts = []
        for n in getattr(struct, "nodes", []) or []:
            pid = n.get("id")
            pname = n.get("label") or pid
            if pid and pid not in parts:
                parts.append(pid)
                lines.append(f"participant {pid} as \"{pname}\"")

        # edges -> messages. Use explicit 'order' if present, otherwise list order
        edges = list(getattr(struct, "edges", []) or [])
        # sort by explicit 'order' if available
        try:
            edges = sorted(edges, key=lambda x: x.get("order", 0))
        except Exception:
            pass

        for e in edges:
            s = e.get("source")
            t = e.get("target")
            if not s or not t:
                continue
            lbl = e.get("label") or e.get("message") or "call"
            # use ->> for call semantics
            lines.append(f"{s} ->> {t}: {lbl}")

        return "\n".join(lines)

    # fallback to flowchart
    lines = ["flowchart LR"]
    nodes = sorted(struct.nodes, key=lambda n: n.get("id"))
    for n in nodes:
        nid = n.get("id")
        label = n.get("label", nid)
        lines.append(f"    {nid}[\"{label}\"]")

    edges = sorted(struct.edges, key=lambda e: (e.get("source"), e.get("target")))
    for e in edges:
        s = e.get("source")
        t = e.get("target")
        lbl = e.get("label") or ""
        if lbl:
            lines.append(f"    {s} -->|{lbl}| {t}")
        else:
            lines.append(f"    {s} --> {t}")

    return "\n".join(lines)


def structural_to_structurizr(struct: StructuralIR) -> str:
    """Produce a minimal Structurizr-like JSON workspace (POC).

    For the POC we return a JSON string that structurizr CLI could consume.
    """
    data = {
        "workspace": {
            "name": "generated",
            "model": {
                "elements": [],
                "relationships": [],
            },
        }
    }
    for n in struct.nodes:
        data["workspace"]["model"]["elements"].append({
            "id": n.get("id"), "name": n.get("label", n.get("id")), "type": n.get("type", "Component")
        })
    for e in struct.edges:
        data["workspace"]["model"]["relationships"].append({
            "sourceId": e.get("source"), "destinationId": e.get("target"), "description": e.get("label", "")
        })

    import json

    return json.dumps(data, indent=2, sort_keys=True)


def structural_to_plantuml(struct: StructuralIR) -> str:
    lines = ["@startuml"]
    for n in sorted(struct.nodes, key=lambda x: x.get("id")):
        nid = n.get("id")
        label = n.get("label", nid)
        lines.append(f"rectangle \"{label}\" as {nid}")
    for e in sorted(struct.edges, key=lambda x: (x.get("source"), x.get("target"))):
        s = e.get("source")
        t = e.get("target")
        lbl = e.get("label") or ""
        if lbl:
            lines.append(f"{s} --> {t} : {lbl}")
        else:
            lines.append(f"{s} --> {t}")
    lines.append("@enduml")
    return "\n".join(lines)
