from __future__ import annotations

import re
from typing import Dict, List, Tuple
from src.ir.semantic_ir import SemanticIR, SystemBoundary, Component, Relationship


_NAME_MAP: List[Tuple[str, str]] = [
    ("postgres", "Metadata Layer"),
    ("db", "Metadata Layer"),
    ("metadata", "Metadata Layer"),
    ("kafka", "Streaming Layer"),
    ("cdc", "Streaming Layer"),
    ("spark", "Compute Layer"),
    ("trino", "Compute Layer"),
    ("object store", "Storage Layer"),
    ("iceberg", "Storage Layer"),
    ("superset", "Analytics Layer"),
    ("bi", "Analytics Layer"),
    ("vault", "Security Layer"),
    ("observability", "Monitoring Layer"),
    ("prometheus", "Monitoring Layer"),
    ("airflow", "Compute Layer"),
    ("keycloak", "Security Layer"),
    ("sso", "Security Layer"),
    ("ingress", "Edge"),
    ("load balancer", "Edge"),
    ("objectstore", "Storage Layer"),
    ("minio", "Storage Layer"),
    ("kafka topics", "Streaming Layer"),
]


def _pick_layer_for_component(c: Component) -> str | None:
    name = (c.name or "").lower()
    # role-based hints
    typ = (c.type or "").lower()
    if typ == "data_store":
        return "Storage Layer"
    if typ == "service":
        return "Compute Layer"
    if typ == "external":
        return "External Integrations"
    if typ == "security":
        return "Security Layer"
    if typ == "observability":
        return "Monitoring Layer"

    for kw, layer in _NAME_MAP:
        if kw in name:
            return layer
    return None


def cluster_ir(ir: SemanticIR, *, min_isolated_trigger: int = 5, mandatory_collapse_threshold: int = 8) -> SemanticIR:
    """Cluster semantically related components into SystemBoundary groups.

    Rules implemented from specs_v45:
    - Name-based mapping and type-based mapping.
    - Relation-based proximity: nodes sharing 2+ upstream parents are grouped.
    - Over-fragmentation: if isolated nodes exceed thresholds, trigger grouping.
    - Create synthetic SystemBoundary nodes and move children under them.
    - Adjust relationships to point to group entry where applicable.
    """
    # Map component id -> component
    comp_map: Dict[str, Component] = {c.id: c for c in ir.components}

    # Build incoming adjacency: target -> list of sources
    incoming: Dict[str, List[str]] = {}
    for r in ir.relationships:
        incoming.setdefault(r.target, []).append(r.source)

    # Detect isolated nodes (no in and no out)
    has_in = set(incoming.keys())
    has_out = set(r.source for r in ir.relationships)
    isolated = [cid for cid in comp_map.keys() if cid not in has_in and cid not in has_out]

    # Decide whether to apply clustering
    apply_clustering = len(isolated) >= min_isolated_trigger

    # grouping result: layer name -> list of component ids
    groups: Dict[str, List[str]] = {}

    # First pass: name/type based grouping
    for cid, comp in comp_map.items():
        layer = _pick_layer_for_component(comp)
        if layer:
            groups.setdefault(layer, []).append(cid)

    # Second pass: relation-based proximity
    # If multiple nodes share 2+ upstreams, group them under a shared parent
    # Keyed by tuple(sorted(upstream_ids))
    proximity: Dict[Tuple[str, ...], List[str]] = {}
    for cid in comp_map.keys():
        ups = tuple(sorted(set(incoming.get(cid, []))))
        if len(ups) >= 2:
            proximity.setdefault(ups, []).append(cid)
    for ups, members in proximity.items():
        if len(members) >= 2:
            name = f"Shared_{'_'.join(ups)}"
            groups.setdefault(name, []).extend(members)

    # Token-based grouping for isolated nodes: find common tokens across isolated nodes
    if apply_clustering:
        token_counts: Dict[str, List[str]] = {}
        for cid in isolated:
            comp = comp_map[cid]
            tokens = [t for t in re.split(r"[^A-Za-z0-9]+", comp.name.lower()) if t and len(t) > 1]
            for t in tokens:
                token_counts.setdefault(t, []).append(cid)
        # Create groups for tokens that appear in 2+ isolated components and are meaningful
        for token, members in token_counts.items():
            if len(members) >= 2 and token not in ("service", "cluster", "prod", "dr", "dc"):
                # map token to a friendly layer name if possible
                mapped = None
                for kw, layer in _NAME_MAP:
                    if kw in token:
                        mapped = layer
                        break
                group_name = mapped or token.capitalize()
                groups.setdefault(group_name, []).extend(members)

        # If still many isolated nodes, create a Miscellaneous group (mandatory collapse)
        remaining_isolated = [cid for cid in isolated if cid not in sum((v for v in groups.values()), [])]
        if len(remaining_isolated) >= mandatory_collapse_threshold:
            groups.setdefault("Miscellaneous", []).extend(remaining_isolated)

    # If too many isolated nodes and no groups yet, attempt to cluster isolated by simple heuristics
    if apply_clustering and not groups:
        # use simple name heuristics to form minimal groups
        for cid in isolated:
            comp = comp_map[cid]
            layer = _pick_layer_for_component(comp) or "Miscellaneous"
            groups.setdefault(layer, []).append(cid)

    # Mandatory collapse if count exceeds threshold
    if len(isolated) >= mandatory_collapse_threshold:
        groups.setdefault("Miscellaneous", []).extend([c for c in isolated if c not in sum((v for v in groups.values()), [])])

    if not groups:
        return ir

    # Create synthetic boundaries and move children
    existing_boundary_ids = {b.id for b in ir.boundaries}
    new_boundaries: List[SystemBoundary] = list(ir.boundaries)
    moved = set()
    for layer_name, members in groups.items():
        # make an id
        bid = layer_name.lower().replace(" ", "_")
        if bid in existing_boundary_ids:
            # append unique suffix
            suffix = 1
            while f"{bid}_{suffix}" in existing_boundary_ids:
                suffix += 1
            bid = f"{bid}_{suffix}"
        new_boundary = SystemBoundary(id=bid, name=layer_name, children=[], synthetic=True)
        for cid in sorted(set(members)):
            if cid in comp_map:
                new_boundary.children.append(cid)
                moved.add(cid)
        if new_boundary.children:
            new_boundaries.append(new_boundary)
            existing_boundary_ids.add(new_boundary.id)

    # Remove moved components from top-level components list? Keep components but they are now children of boundaries.
    # Adjust relationships: for any rel from external actors into moved leaf nodes, re-route to the boundary entry
    new_relationships: List[Relationship] = []
    boundary_of: Dict[str, str] = {}
    for b in new_boundaries:
        for child in b.children:
            boundary_of[child] = b.id

    for r in ir.relationships:
        src = r.source
        tgt = r.target
        # If target is moved into a boundary and source is external (not in same boundary), route to boundary
        if tgt in boundary_of and boundary_of.get(src) != boundary_of.get(tgt):
            new_target = boundary_of[tgt]
            new_relationships.append(Relationship(source=src, target=new_target, type=r.type, label=r.label, direction=r.direction, order=r.order, metadata={**r.metadata, "routed_to_group": True}))
        else:
            new_relationships.append(r)

    # Ensure no external actors pointing directly to leaf nodes where possible: for any relationship from an actor id that matches prefix 'external' or component.type=='external'
    # (We keep it simple: reroute sources with 'external' in id or component.type=='external')
    final_relationships: List[Relationship] = []
    for r in new_relationships:
        src_comp = comp_map.get(r.source)
        if src_comp and src_comp.type == "external" and r.target in boundary_of:
            final_relationships.append(Relationship(source=r.source, target=boundary_of[r.target], type=r.type, label=r.label, direction=r.direction, order=r.order, metadata=r.metadata))
        else:
            final_relationships.append(r)

    # Replace boundaries and relationships in IR
    ir.boundaries = new_boundaries
    ir.relationships = final_relationships

    # Post-processing: ensure no leaf node exists without incoming edge or group membership
    comp_ids = {c.id for c in ir.components}
    children_in_groups = set(sum([b.children for b in ir.boundaries], []))
    # nodes with incoming edges
    nodes_with_in = set(incoming.keys())

    ungrouped_leafs = [cid for cid in comp_ids if cid not in children_in_groups and cid not in nodes_with_in]

    # Exemptions: components tagged as explicitly external_isolated via type or tags
    def _is_exempt(cid: str) -> bool:
        c = comp_map.get(cid)
        if not c:
            return True
        if getattr(c, "type", "").lower() in ("external_isolated", "external"):
            return True
        if "external_isolated" in getattr(c, "tags", []):
            return True
        return False

    to_move = [cid for cid in ungrouped_leafs if not _is_exempt(cid)]
    if to_move:
        misc_id = "miscellaneous"
        suffix = 1
        existing_ids = {b.id for b in ir.boundaries}
        base = misc_id
        while misc_id in existing_ids:
            misc_id = f"{base}_{suffix}"
            suffix += 1
        misc_boundary = SystemBoundary(id=misc_id, name="Miscellaneous", children=[], synthetic=True)
        for cid in sorted(set(to_move)):
            misc_boundary.children.append(cid)
            moved.add(cid)
        ir.boundaries.append(misc_boundary)

        # Reroute any relationships that point to these leafs from external sources to the misc group
        rerouted: List[Relationship] = []
        for r in ir.relationships:
            if r.target in misc_boundary.children and (r.source not in comp_ids or _is_exempt(r.source)):
                rerouted.append(Relationship(source=r.source, target=misc_boundary.id, type=r.type, label=r.label, direction=r.direction, order=r.order, metadata={**r.metadata, "routed_to_group": True}))
            else:
                rerouted.append(r)
        ir.relationships = rerouted

    # attach metadata about clustering
    ir.metadata.setdefault("clustering", {})
    ir.metadata["clustering"]["groups"] = {k: v for k, v in groups.items()}
    ir.metadata["clustering"]["moved_count"] = len(moved)

    # Layout hints per spec_v45
    ir.metadata.setdefault("layout_policy", [
        "Users",
        "Ingress",
        "Application Layer",
        "Compute Layer",
        "Data Layer",
        "Observability",
        "Security",
    ])

    return ir
