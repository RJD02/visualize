"""Simple PlantUML sequence diagram generator from architecture plan."""
from typing import Any, Dict, List
import re


def generate_plantuml_sequence_from_architecture(architecture_plan: Dict[str, Any]) -> str:
    """
    Generate PlantUML sequence diagram directly from architecture plan.
    No LLM needed - just extracts components and creates a realistic flow.
    """
    systems = architecture_plan.get("systems", [])
    services = architecture_plan.get("services", [])
    actors = architecture_plan.get("actors", [])
    data_stores = architecture_plan.get("data_stores", [])

    lines: List[str] = ["@startuml", ""]

    def _sanitize_id(raw: str) -> str:
        s = re.sub(r"[^0-9a-zA-Z_]+", "_", raw or "node").strip("_")
        if not s:
            s = "node"
        # ensure it doesn't start with a digit
        if s[0].isdigit():
            s = f"n_{s}"
        return s

    # Build ordered participants list (kind, id, name)
    participants: List[Dict[str, str]] = []
    used_ids = set()

    def _add_part(kind: str, item: Dict[str, Any], default_name: str):
        raw_id = item.get("id") or item.get("name") or default_name
        base = _sanitize_id(str(raw_id))
        pid = base
        idx = 1
        while pid in used_ids:
            idx += 1
            pid = f"{base}_{idx}"
        used_ids.add(pid)
        pname = item.get("name") or default_name
        participants.append({"kind": kind, "id": pid, "name": pname})

    for a in actors:
        _add_part("actor", a, "User")
    for s in systems:
        _add_part("participant", s, "System")
    for sv in services:
        _add_part("participant", sv, "Service")
    for d in data_stores:
        _add_part("database", d, "Database")

    # If no participants found, create a default actor and a default participant
    if not participants:
        participants.append({"kind": "actor", "id": "user", "name": "User"})
        participants.append({"kind": "participant", "id": "system", "name": "System"})

    # Emit participant declarations
    for p in participants[:8]:  # limit to a reasonable number
        if p["kind"] == "actor":
            lines.append(f'actor "{p["name"]}" as {p["id"]}')
        elif p["kind"] == "database":
            lines.append(f'database "{p["name"]}" as {p["id"]}')
        else:
            lines.append(f'participant "{p["name"]}" as {p["id"]}')

    lines.append("")

    # Build a simple chain-like interaction: start from first actor if present
    # Otherwise start from the first participant
    start = None
    for p in participants:
        if p["kind"] == "actor":
            start = p
            break
    if not start:
        start = participants[0]

    prev = start
    # Walk the remaining participants and create calls
    for p in participants[1:6]:
        lines.append(f'{prev["id"]} -> {p["id"]}: call')
        lines.append(f'activate {p["id"]}')
        # if calling a database, show query/response
        if p["kind"] == "database":
            lines.append(f'{p["id"]} --> {prev["id"]}: data')
        else:
            lines.append(f'{p["id"]} --> {prev["id"]}: ok')
        lines.append(f'deactivate {p["id"]}')
        prev = p

    # Final response back to the actor (if not already)
    if prev and start and prev["id"] != start["id"]:
        lines.append(f'{prev["id"]} --> {start["id"]}: final')

    lines.append("")
    lines.append("@enduml")

    return "\n".join(lines)
