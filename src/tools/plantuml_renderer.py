"""PlantUML renderer tool."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from uuid import UUID

from src.models.architecture_plan import ArchitecturePlan
from src.renderer import render_plantuml, render_plantuml_svg
from src.renderers.mermaid_renderer import render_mermaid_svg
from src.services.styling_audit_service import record_styling_audit
from src.tools.diagram_validator import validate_and_sanitize
from src.utils.config import settings
from src.utils.file_utils import ensure_dir


_DEFAULT_DIAGRAM_TYPE = "system_context"


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


def generate_plantuml_from_plan(
    plan: ArchitecturePlan,
    overrides: dict | None = None,
    diagram_types: List[str] | None = None,
) -> List[dict]:
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

    requested_views: List[str]
    if diagram_types:
        requested_views = [view.strip() for view in diagram_types if view]
    else:
        requested_views = list(plan.diagram_views)
    if not requested_views:
        requested_views = [_DEFAULT_DIAGRAM_TYPE]

    for view in requested_views:
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
        diagram_text = "\n".join(parts)
        diagrams.append(
            {
                "type": view,
                "plantuml": diagram_text,
                "llm_diagram": diagram_text,
                "format": "plantuml",
                "schema_version": 1,
            }
        )
    return diagrams


def render_diagrams(
    diagrams: List[dict],
    output_name: str,
    output_format: str = "svg",
    audit_context: Dict[str, Any] | None = None,
) -> List[str]:
    output_dir = ensure_dir(settings.output_dir)
    files = []
    for idx, diagram in enumerate(diagrams):
        diagram_type = diagram.get("type", "diagram").replace(" ", "_")
        file_name = f"{output_name}_{diagram_type}_{idx + 1}"
        llm_payload = diagram.get("llm_diagram")
        llm_text: str | None = None
        fmt = diagram.get("format")
        if isinstance(llm_payload, dict):
            fmt = llm_payload.get("format") or fmt
            llm_text = (llm_payload.get("diagram") or llm_payload.get("text") or "").strip() or None
        elif llm_payload:
            llm_text = str(llm_payload)
        if not llm_text:
            plantuml_text = diagram.get("plantuml")
            if plantuml_text:
                llm_text = plantuml_text
                fmt = fmt or "plantuml"

        if llm_text:
            image_path, sanitized_text, warnings, resolved_fmt = _render_llm_diagram(
                llm_text,
                fmt,
                file_name,
                output_dir,
                output_format,
            )
            files.append(str(image_path))
            _maybe_record_llm_audit(
                audit_context,
                diagram_plan_id=diagram.get("plan_id"),
                diagram_type=diagram.get("type"),
                llm_format=resolved_fmt,
                llm_text=llm_text,
                sanitized_text=sanitized_text,
                warnings=warnings,
            )
            continue

        plantuml = diagram.get("plantuml") or "@startuml\n@enduml"
        _validate_pure_plantuml(plantuml)
        if output_format == "svg":
            image_path = render_plantuml_svg(plantuml, file_name)
        else:
            image_path = render_plantuml(plantuml, file_name)
        files.append(str(image_path))
        puml_path = Path(output_dir) / f"{file_name}.puml"
        puml_path.write_text(plantuml, encoding="utf-8")
    return files


def render_diagram_by_type(diagrams: List[dict], diagram_type: str, output_name: str, output_format: str = "svg") -> List[str]:
    selected = [d for d in diagrams if d.get("type") == diagram_type]
    if not selected:
        return []
    return render_diagrams(selected, output_name, output_format=output_format)


def _coerce_uuid(value: UUID | str | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _render_llm_diagram(
    diagram_text: str,
    diagram_format: str | None,
    file_name: str,
    output_dir: Path,
    output_format: str,
) -> tuple[str, str, List[str], str]:
    fmt_token = (diagram_format or "plantuml").strip().lower()
    if fmt_token.startswith("plant"):
        fmt = "plantuml"
    elif fmt_token.startswith("mermaid"):
        fmt = "mermaid"
    else:
        raise ValueError(f"Unsupported diagram format '{diagram_format}'")

    validation = validate_and_sanitize(diagram_text, fmt)
    sanitized = validation.sanitized_text
    warnings = validation.warnings

    if fmt == "plantuml":
        if output_format == "svg":
            image_path = render_plantuml_svg(sanitized, file_name)
        else:
            image_path = render_plantuml(sanitized, file_name)
        (output_dir / f"{file_name}.puml").write_text(sanitized, encoding="utf-8")
        return str(image_path), sanitized, warnings, fmt

    if output_format != "svg":
        raise ValueError("Mermaid diagrams only support SVG output")
    svg_text = render_mermaid_svg(sanitized)
    svg_path = output_dir / f"{file_name}.svg"
    svg_path.write_text(svg_text, encoding="utf-8")
    (output_dir / f"{file_name}.mmd").write_text(sanitized, encoding="utf-8")
    return str(svg_path), sanitized, warnings, fmt


def _maybe_record_llm_audit(
    audit_context: Dict[str, Any] | None,
    *,
    diagram_plan_id: str | UUID | None,
    diagram_type: str | None,
    llm_format: str,
    llm_text: str,
    sanitized_text: str,
    warnings: List[str],
) -> None:
    if not audit_context:
        return
    db = audit_context.get("db")
    session_id = _coerce_uuid(audit_context.get("session_id"))
    plan_id = diagram_plan_id or audit_context.get("plan_id")
    if not (db and session_id and plan_id):
        return
    record_styling_audit(
        db,
        session_id=session_id,
        plan_id=plan_id,
        diagram_id=None,
        diagram_type=diagram_type,
        user_prompt=audit_context.get("user_prompt"),
        llm_format=llm_format,
        llm_diagram=llm_text,
        sanitized_diagram=sanitized_text,
        extracted_intent=None,
        styling_plan=None,
        execution_steps=[f"Validated {llm_format} diagram before rendering."],
        agent_reasoning="render_diagrams defaulted to llm_diagram input.",
        mode="pre-svg",
        renderer_input_before=llm_text,
        renderer_input_after=sanitized_text,
        svg_before=None,
        svg_after=None,
        validation_warnings=warnings,
        blocked_tokens=[],
    )


def render_llm_plantuml(
    diagram_text: str,
    output_name: str,
    *,
    diagram_type: str | None = None,
    output_format: str = "svg",
) -> dict:
    """Render PlantUML supplied directly by an LLM after validation."""
    validation = validate_and_sanitize(diagram_text, "plantuml")
    if output_format == "svg":
        image_path = render_plantuml_svg(validation.sanitized_text, output_name)
    else:
        image_path = render_plantuml(validation.sanitized_text, output_name)
    output_dir = ensure_dir(settings.output_dir)
    puml_path = Path(output_dir) / f"{output_name}.puml"
    puml_path.write_text(validation.sanitized_text, encoding="utf-8")
    return {
        "file_path": str(image_path),
        "diagram_type": diagram_type,
        "sanitized_text": validation.sanitized_text,
        "warnings": validation.warnings,
    }
