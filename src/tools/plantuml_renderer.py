"""PlantUML renderer tool."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from src.models.architecture_plan import ArchitecturePlan
from src.renderer import render_plantuml, render_plantuml_svg
from src.utils.config import settings
from src.utils.file_utils import ensure_dir


def _validate_pure_plantuml(plantuml: str) -> None:
    lowered = plantuml.lower()
    disallowed = ["skinparam", "!theme", "skinparam", "style", "linetype", "shadowing", "bgcolor"]
    if any(token in lowered for token in disallowed):
        raise ValueError("PlantUML contains aesthetic directives. Structural diagrams must be neutral.")


def _sanitize_name(name: str) -> str:
    return name.replace(" ", "_").replace("-", "_")


def _alias_for(label: str, used: Dict[str, int]) -> str:
    base = _sanitize_name(label) or "item"
    if not base[0].isalpha():
        base = f"n_{base}"
    base = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in base)
    count = used.get(base, 0)
    used[base] = count + 1
    return base if count == 0 else f"{base}_{count}"


def _diagram_header(plan: ArchitecturePlan, layout_override: str | None = None) -> str:
    layout = layout_override or plan.visual_hints.layout
    direction = "left to right direction" if layout == "left-to-right" else "top to bottom direction"
    return f"@startuml\n{direction}\n"


def _zone_block(title: str, items: List[str], alias: str, aliases: Dict[str, str]) -> str:
    lines = [f"package \"{title}\" as {alias} {{"]
    for item in items:
        item_alias = aliases[item]
        lines.append(f"  component \"{item}\" as {item_alias}")
    lines.append("}")
    return "\n".join(lines)


def _zone_items_for_view(plan: ArchitecturePlan, view: str) -> Dict[str, List[str]]:
    zones = {
        "clients": list(plan.zones.clients),
        "edge": list(plan.zones.edge),
        "core_services": list(plan.zones.core_services),
        "external_services": list(plan.zones.external_services),
        "data_stores": list(plan.zones.data_stores),
    }
    if view == "system_context":
        return {zone: (items[:1] if items else []) for zone, items in zones.items()}
    if view == "container":
        return {"edge": zones.get("edge", []), "core_services": zones.get("core_services", []), "data_stores": zones.get("data_stores", [])}
    if view == "component":
        return {"core_services": zones.get("core_services", [])}
    if view in {"sequence", "runtime"}:
        return {"clients": zones.get("clients", []), "edge": zones.get("edge", []), "core_services": zones.get("core_services", [])}
    return {zone: items for zone, items in zones.items()}


def _relationships(plan: ArchitecturePlan, aliases: Dict[str, str]) -> List[str]:
    rels = []
    for rel in plan.relationships:
        arrow = "-->" if rel.type != "async" else "..>"
        from_alias = aliases.get(rel.from_, rel.from_)
        to_alias = aliases.get(rel.to, rel.to)
        rels.append(f"{from_alias} {arrow} {to_alias} : {rel.type}")
    return rels


def generate_plantuml_from_plan(plan: ArchitecturePlan, overrides: dict | None = None) -> List[dict]:
    overrides = overrides or {}
    layout_override = overrides.get("layout")
    zone_order = overrides.get("zone_order")
    diagrams = []
    zone_map = {
        "clients": plan.zones.clients,
        "edge": plan.zones.edge,
        "core_services": plan.zones.core_services,
        "external_services": plan.zones.external_services,
        "data_stores": plan.zones.data_stores,
    }
    default_order = ["clients", "edge", "core_services", "external_services", "data_stores"]
    if isinstance(zone_order, list) and zone_order:
        ordered = [z for z in zone_order if z in zone_map]
        for z in default_order:
            if z not in ordered:
                ordered.append(z)
        zone_order = ordered
    else:
        zone_order = default_order

    labels: List[str] = []
    for items in zone_map.values():
        labels.extend(list(items))
    for rel in plan.relationships:
        labels.extend([rel.from_, rel.to])
    used: Dict[str, int] = {}
    aliases: Dict[str, str] = {}
    for label in labels:
        if label not in aliases:
            aliases[label] = _alias_for(label, used)

    for view in plan.diagram_views:
        header = _diagram_header(plan, layout_override=layout_override)
        parts = [header]
        items_map = _zone_items_for_view(plan, view)
        node_to_zone: Dict[str, str] = {}
        for zone_name, items in zone_map.items():
            for item in items:
                node_to_zone[item] = zone_name
        for rel in plan.relationships:
            for endpoint in (rel.from_, rel.to):
                zone = node_to_zone.get(endpoint)
                if not zone:
                    continue
                items = items_map.setdefault(zone, [])
                if endpoint not in items:
                    items.append(endpoint)
        if plan.visual_hints.group_by_zone:
            zone_aliases: List[str] = []
            for zone_name in zone_order:
                items = items_map.get(zone_name, [])
                if items:
                    alias = f"zone_{zone_name}"
                    parts.append(_zone_block(zone_name, items, alias, aliases))
                    zone_aliases.append(alias)
            for idx in range(len(zone_aliases) - 1):
                parts.append(f"{zone_aliases[idx]} -[hidden]-> {zone_aliases[idx + 1]}")
        else:
            flat = []
            for zone in ["clients", "edge", "core_services", "external_services", "data_stores"]:
                flat.extend(items_map.get(zone, []))
            for item in flat:
                item_alias = aliases[item]
                parts.append(f"component \"{item}\" as {item_alias}")
        # relationships are not filtered by view currently; they connect existing items
        parts.extend(_relationships(plan, aliases))
        parts.append("@enduml")
        diagrams.append({"type": view, "plantuml": "\n".join(parts)})
    return diagrams


def render_diagrams(diagrams: List[dict], output_name: str, output_format: str = "png") -> List[str]:
    output_dir = ensure_dir(settings.output_dir)
    files = []
    for idx, diagram in enumerate(diagrams):
        diagram_type = diagram.get("type", "diagram").replace(" ", "_")
        file_name = f"{output_name}_{diagram_type}_{idx + 1}"
        plantuml = diagram.get("plantuml", "@startuml\n@enduml")
        _validate_pure_plantuml(plantuml)
        if output_format == "svg":
            image_path = render_plantuml_svg(plantuml, file_name)
        else:
            image_path = render_plantuml(plantuml, file_name)
        files.append(str(image_path))
        puml_path = Path(output_dir) / f"{file_name}.puml"
        puml_path.write_text(plantuml, encoding="utf-8")
    return files


def render_diagram_by_type(diagrams: List[dict], diagram_type: str, output_name: str, output_format: str = "png") -> List[str]:
    selected = [d for d in diagrams if d.get("type") == diagram_type]
    if not selected:
        return []
    return render_diagrams(selected, output_name, output_format=output_format)
