"""Deterministic IR enrichment helpers (spec v34)."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from jsonschema import Draft202012Validator

DEFAULT_PALETTE = [
    "#FDE68A",
    "#FBCFE8",
    "#E0E7FF",
    "#DB2777",
    "#0F172A",
]
FONT_FAMILY = "Inter, Arial, sans-serif"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "specs" / "ir_enriched_schema_v1.json"

ROLE_BY_ZONE = {
    "clients": "actor",
    "edge": "gateway",
    "core_services": "service",
    "external_services": "external",
    "data_stores": "data_store",
}

TYPE_BY_ROLE = {
    "actor": "actor",
    "gateway": "container",
    "service": "container",
    "external": "external",
    "data_store": "data_store",
}

SHAPE_BY_TYPE = {
    "actor": "circular",
    "container": "rounded",
    "component": "rectangle",
    "data_store": "cylinder",
    "external": "cloud",
    "system": "rectangle",
}

SIZE_BY_TYPE = {
    "actor": "small",
    "container": "medium",
    "component": "medium",
    "data_store": "medium",
    "external": "medium",
    "system": "large",
}

STEREOTYPE_BY_ROLE = {
    "actor": "person",
    "gateway": "ingress",
    "service": "api",
    "external": "integration",
    "data_store": "database",
}

PLANTUML_SHAPE_BY_TYPE = {
    "actor": "actor",
    "container": "component",
    "component": "component",
    "data_store": "database",
    "external": "cloud",
    "system": "component",
}

MERMAID_TYPE_BY_TYPE = {
    "actor": "actor",
    "container": "class",
    "component": "class",
    "data_store": "entity",
    "external": "subgraph",
    "system": "class",
}

EDGE_PRESETS = {
    "sync": {"style": "solid", "arrowhead": "normal", "curvature": 0.0, "palette_index": -1},
    "async": {"style": "dashed", "arrowhead": "open", "curvature": 0.0, "palette_index": 1},
    "data": {"style": "dashed", "arrowhead": "open", "curvature": 0.1, "palette_index": 3},
    "auth": {"style": "solid", "arrowhead": "normal", "curvature": 0.0, "palette_index": 2},
}

ALLOWED_MOODS = {"minimal", "vibrant", "formal", "playful"}
ALLOWED_DENSITY = {"compact", "balanced", "spacious"}

DEFAULT_ZONE_ORDER = ["clients", "edge", "core_services", "external_services", "data_stores"]

# Zone pairs that should be connected when no explicit edge bridges them (Rule 1).
_ZONE_CASCADE_PAIRS: List[Tuple[str, str]] = [
    ("clients", "edge"),
    ("edge", "core_services"),
    ("core_services", "data_stores"),
    ("external_services", "core_services"),
]

# (from_keyword, to_keyword, rel_type, reason, confidence) — Rule 2 tech-dependency patterns.
# Labels are lowercased before matching.  First match per pair wins.
_TECH_DEPS: List[Tuple[str, str, str, str, float]] = [
    ("kafka",      "consumer",   "async", "kafka feeds consumer",            0.7),
    ("kafka",      "processor",  "async", "kafka feeds processor",           0.7),
    ("kafka",      "worker",     "async", "kafka feeds worker",              0.7),
    ("streaming",  "consumer",   "async", "streaming feeds consumer",        0.7),
    ("streaming",  "processor",  "async", "streaming feeds processor",       0.7),
    ("producer",   "kafka",      "async", "producer publishes to kafka",     0.7),
    ("producer",   "streaming",  "async", "producer publishes to streaming", 0.7),
    ("prometheus", "grafana",    "data",  "prometheus scrapes to grafana",   0.7),
    ("metrics",    "grafana",    "data",  "metrics flow to grafana",         0.7),
    ("airflow",    "spark",      "async", "airflow orchestrates spark",      0.7),
    ("scheduler",  "spark",      "async", "scheduler triggers spark",        0.7),
    ("scheduler",  "worker",     "async", "scheduler dispatches to worker",  0.7),
    ("ingress",    "service",    "sync",  "ingress routes to service",       0.7),
    ("gateway",    "service",    "sync",  "gateway routes to service",       0.7),
    ("service",    "postgres",   "data",  "service reads/writes postgres",   0.7),
    ("service",    "mysql",      "data",  "service reads/writes mysql",      0.7),
    ("service",    "mongo",      "data",  "service reads/writes mongo",      0.7),
    ("service",    "redis",      "data",  "service uses redis cache",        0.7),
    ("primary",    "replica",    "data",  "primary replicates to replica",   0.7),
    ("primary",    "secondary",  "data",  "primary replicates to secondary", 0.7),
    ("dc",         "dr",         "data",  "dc replicates to dr site",        0.7),
]
LAYOUT_MAP = {
    "left-to-right": "left-right",
    "left_right": "left-right",
    "left-right": "left-right",
    "right-to-left": "right-left",
    "right_left": "right-left",
    "top-down": "top-down",
    "top_down": "top-down",
    "bottom-up": "bottom-up",
    "bottom_up": "bottom-up",
    "grid": "grid",
}


class IREnrichmentError(RuntimeError):
    """Raised when deterministic enrichment fails validation."""


def enrich_ir(input_ir: Dict[str, object]) -> Dict[str, object]:
    """Produce an enriched IR payload that satisfies the v34 schema."""
    builder = _IREnricher(input_ir or {})
    enriched = builder.build()
    errors = validate_enriched_ir(enriched)
    if errors:
        raise IREnrichmentError("; ".join(errors))
    return enriched


def validate_enriched_ir(payload: Dict[str, object], schema_path: Optional[Path] = None) -> List[str]:
    """Validate payload against the enriched IR schema and return error messages."""
    schema = _load_schema(schema_path or SCHEMA_PATH)
    validator = Draft202012Validator(schema)
    errors = []
    for err in sorted(validator.iter_errors(payload), key=lambda e: e.path):
        location = "/".join(str(part) for part in err.path) or "<root>"
        errors.append(f"{location}: {err.message}")
    return errors


class _IREnricher:
    def __init__(self, source: Dict[str, object]):
        self.source = source
        self.diagram_type = self._diagram_type()
        self.layout = self._layout()
        self.aesthetic_intent = self._extract_aesthetic_intent()
        self.palette = self._derive_palette()
        self.relationships = list(self._coerce_list(source.get("relationships")))
        self.zone_data = self._coerce_zones(source.get("zones"))
        self.zone_order = self._build_zone_order()
        self.zone_colors = self._assign_zone_colors()
        self.node_ids: set[str] = set()
        self.edge_ids: set[str] = set()
        self.nodes: List[Dict[str, object]] = []
        self.edges: List[Dict[str, object]] = []
        self.validation_messages: List[Dict[str, str]] = []
        self.node_lookup: Dict[str, Dict[str, object]] = {}
        # Records of inferred edges for explainability (not in enriched output — schema compliant)
        self.inference_log: List[Dict[str, object]] = []

    def build(self) -> Dict[str, object]:
        self._populate_nodes()
        self._populate_relationship_nodes()
        self._populate_edges()
        self._infer_missing_connections()
        self._sort_nodes()
        return {
            "diagram_type": self.diagram_type,
            "layout": self.layout,
            "zone_order": self.zone_order,
            "nodes": self.nodes,
            "edges": self.edges,
            "nodeIntent": self._node_intent(),
            "edgeIntent": self._edge_intent(),
            "globalIntent": self._global_intent(),
            "metadata": self._metadata(),
        }

    def _diagram_type(self) -> str:
        explicit = str(self.source.get("diagram_type") or "").strip()
        if explicit:
            return explicit
        views = self._coerce_list(self.source.get("diagram_views"))
        return str(views[0]) if views else "diagram"

    def _layout(self) -> str:
        hints = self.source.get("visual_hints") or {}
        layout_hint = str(self.source.get("layout") or hints.get("layout") or "top-down")
        normalized = layout_hint.replace(" ", "-").lower()
        return LAYOUT_MAP.get(normalized, "top-down")

    def _extract_aesthetic_intent(self) -> Dict[str, object]:
        intent = self.source.get("aesthetic_intent") or self.source.get("semantic_intent")
        return intent or {}

    def _derive_palette(self) -> List[str]:
        palette = []
        metadata = self.aesthetic_intent.get("metadata") if isinstance(self.aesthetic_intent, dict) else None
        user_palette = None
        if isinstance(metadata, dict):
            user_palette = metadata.get("userPalette")
        if user_palette is None and isinstance(self.aesthetic_intent, dict):
            user_palette = self.aesthetic_intent.get("userPalette")
        palette = [_normalize_color(value) for value in self._coerce_list(user_palette)] if user_palette else []
        palette = [color for color in palette if color]
        if len(palette) < 2:
            palette.extend([c for c in DEFAULT_PALETTE if c not in palette])
        if len(palette) > 8:
            palette = palette[:8]
        return palette or DEFAULT_PALETTE

    @staticmethod
    def _coerce_list(value: object) -> List[object]:
        if isinstance(value, list):
            return value
        if value is None:
            return []
        return [value]

    def _coerce_zones(self, zones: object) -> Dict[str, List[str]]:
        data: Dict[str, List[str]] = {}
        if isinstance(zones, dict):
            for key, value in zones.items():
                data[str(key)] = [str(entry) for entry in self._coerce_list(value) if str(entry).strip()]
        return data

    def _build_zone_order(self) -> List[str]:
        explicit = [zone for zone in DEFAULT_ZONE_ORDER if zone in self.zone_data and self.zone_data.get(zone)]
        if explicit:
            return explicit
        if self.zone_data:
            return list(self.zone_data.keys())
        return list(DEFAULT_ZONE_ORDER)

    def _assign_zone_colors(self) -> Dict[str, Dict[str, str]]:
        mapping: Dict[str, Dict[str, str]] = {}
        palette_len = len(self.palette)
        for idx, zone in enumerate(self.zone_order):
            fill = self.palette[idx % palette_len]
            border = self.palette[(idx + 1) % palette_len]
            mapping[zone] = {"fill": fill, "border": border}
        return mapping

    def _populate_nodes(self) -> None:
        for zone in self.zone_order:
            for label in self.zone_data.get(zone, []):
                self._add_node(label, zone, inferred=False)

    def _populate_relationship_nodes(self) -> None:
        for rel in self.relationships:
            for primary, alternate in (("from", "from_"), ("to", None)):
                raw = self._rel_value(rel, primary, alternate)
                label = str(raw or "").strip()
                if not label:
                    continue
                key = _label_key(label)
                if key in self.node_lookup:
                    continue
                self._add_node(label, None, inferred=True)
                self.validation_messages.append({
                    "severity": "warning",
                    "message": f"Inferred node '{label}' from relationship endpoints",
                })

    def _add_node(self, label: str, zone: Optional[str], inferred: bool) -> Dict[str, object]:
        normalized_label = (label or "").strip() or "node"
        key = _label_key(normalized_label)
        if key in self.node_lookup:
            return self.node_lookup[key]
        node_id = _unique_identifier(normalized_label, self.node_ids, prefix="node")
        role, node_type = self._infer_role_and_type(normalized_label, zone)
        shape = SHAPE_BY_TYPE.get(node_type, "rectangle")
        size_hint = SIZE_BY_TYPE.get(node_type, "medium")
        colors = self.zone_colors.get(zone or "", {"fill": self.palette[0], "border": self.palette[1 % len(self.palette)]})
        style = {
            "fillColor": colors["fill"],
            "borderColor": colors["border"],
            "textColor": self.palette[-1],
            "borderWidth": 2,
            "fontSize": 12,
            "fontFamily": FONT_FAMILY,
            "padding": 6 if node_type == "actor" else (10 if node_type == "data_store" else 8),
        }
        node = {
            "node_id": node_id,
            "label": normalized_label,
            "role": role,
            "zone": zone,
            "type": node_type,
            "stereotype": STEREOTYPE_BY_ROLE.get(role),
            "shape": shape,
            "size_hint": size_hint,
            "width": None,
            "height": None,
            "node_style": style,
            "rendering_hints": self._rendering_hints(node_type, colors["fill"], normalized_label),
            "metadata": {
                "confidence": 0.98 if not inferred else 0.8,
                "reason": "explicit zone membership" if not inferred else "derived from relationship",
                "source": f"zones.{zone}" if zone else "relationships",
            },
        }
        self.nodes.append(node)
        self.node_lookup[key] = node
        self.node_ids.add(node_id)
        return node

    def _rendering_hints(self, node_type: str, fill_color: str, label: str) -> Dict[str, object]:
        plantuml_shape = PLANTUML_SHAPE_BY_TYPE.get(node_type, "component")
        mermaid_type = MERMAID_TYPE_BY_TYPE.get(node_type, "class")
        return {
            "plantuml": {
                "plantuml_shape": plantuml_shape,
                "plantuml_color": fill_color,
                "plantuml_label": label,
            },
            "mermaid": {
                "mermaid_type": mermaid_type,
                "mermaid_id": _mermaid_identifier(label),
            },
        }

    def _infer_role_and_type(self, label: str, zone: Optional[str]) -> Tuple[str, str]:
        if zone in ROLE_BY_ZONE:
            role = ROLE_BY_ZONE[zone]
        else:
            role = _role_from_label(label)
        node_type = TYPE_BY_ROLE.get(role, "container")
        return role, node_type

    def _populate_edges(self) -> None:
        for rel in self.relationships:
            from_label = str(self._rel_value(rel, "from", "from_") or "").strip()
            to_label = str(self._rel_value(rel, "to") or "").strip()
            if not from_label or not to_label:
                continue
            from_node = self._ensure_node(from_label)
            to_node = self._ensure_node(to_label)
            rel_type = str(self._rel_value(rel, "type") or "sync").lower()
            description = self._rel_value(rel, "description") or self._rel_value(rel, "label")
            label = str(description or f"{from_label} -> {to_label}")
            preset = EDGE_PRESETS.get(rel_type, EDGE_PRESETS["sync"])
            color = self.palette[preset["palette_index"] % len(self.palette)]
            edge_id = _unique_identifier(
                f"{from_node['node_id']}__{to_node['node_id']}__{rel_type}",
                self.edge_ids,
                prefix="edge",
            )
            text_style = {
                "fontSize": 11,
                "fontFamily": FONT_FAMILY,
                "textColor": color,
            }
            confidence = 0.95 if description else 0.85
            edge = {
                "edge_id": edge_id,
                "from_id": from_node["node_id"],
                "to_id": to_node["node_id"],
                "rel_type": rel_type,
                "label": label,
                "style": preset["style"],
                "color": color,
                "width": 2,
                "arrowhead": preset["arrowhead"],
                "text_style": text_style,
                "curvature": preset.get("curvature", 0.0),
                "confidence": confidence,
                "reason": "explicit relationship" if description else "relationship inferred",
            }
            self.edges.append(edge)

    def _ensure_node(self, label: str) -> Dict[str, object]:
        key = _label_key(label)
        node = self.node_lookup.get(key)
        if node:
            return node
        return self._add_node(label, None, inferred=True)

    def _infer_missing_connections(self) -> None:
        """Infer missing edges to improve diagram connectivity (deterministic, no randomness).

        Rule 1 — Zone cascade: for each adjacent zone pair in _ZONE_CASCADE_PAIRS, if no
            existing edge bridges them, add one weak dashed edge (confidence=0.5).
        Rule 2 — Tech-dependency: known keyword pairs infer typed edges (confidence=0.7).
        Rule 3 — Completion guard: any node still at degree 0 gets one weak edge (confidence=0.3).

        All sorting uses sorted(..., key=str.lower) for determinism.
        Metadata (rule/reason/confidence) is stored in self.inference_log, not on the edge
        dict, to remain schema-compliant (Edge schema has additionalProperties=false).
        """
        if not self.nodes:
            return

        # Degree index (inbound + outbound)
        degree: Dict[str, int] = {n["node_id"]: 0 for n in self.nodes}
        for edge in self.edges:
            degree[edge["from_id"]] = degree.get(edge["from_id"], 0) + 1
            degree[edge["to_id"]] = degree.get(edge["to_id"], 0) + 1

        # Zone → sorted node list
        zone_nodes: Dict[str, List[Dict[str, object]]] = {}
        for zone in self.zone_order:
            zone_nodes[zone] = sorted(
                [n for n in self.nodes if n.get("zone") == zone],
                key=lambda n: n["label"].lower(),
            )

        # Existing from_id→to_id pairs for deduplication
        existing_pairs: set[tuple[str, str]] = {
            (e["from_id"], e["to_id"]) for e in self.edges
        }
        inferred: List[Dict[str, object]] = []

        # ── Rule 1: Zone-layer cascade ──────────────────────────────────────
        for from_zone, to_zone in _ZONE_CASCADE_PAIRS:
            from_nodes = zone_nodes.get(from_zone, [])
            to_nodes = zone_nodes.get(to_zone, [])
            if not from_nodes or not to_nodes:
                continue
            from_ids = {n["node_id"] for n in from_nodes}
            to_ids = {n["node_id"] for n in to_nodes}
            already = any(
                (e["from_id"] in from_ids and e["to_id"] in to_ids)
                or (e["from_id"] in to_ids and e["to_id"] in from_ids)
                for e in self.edges + inferred
            )
            if already:
                continue
            from_node = from_nodes[0]
            to_node = to_nodes[0]
            pair = (from_node["node_id"], to_node["node_id"])
            if pair not in existing_pairs:
                edge = self._make_inferred_edge(
                    from_node, to_node,
                    rel_type="async",
                    rule="zone_cascade",
                    reason=f"zone layer cascade: {from_zone} → {to_zone}",
                    confidence=0.5,
                )
                inferred.append(edge)
                existing_pairs.add(pair)
                degree[from_node["node_id"]] = degree.get(from_node["node_id"], 0) + 1
                degree[to_node["node_id"]] = degree.get(to_node["node_id"], 0) + 1

        # ── Rule 2: Tech-dependency keywords ────────────────────────────────
        sorted_nodes = sorted(self.nodes, key=lambda n: n["label"].lower())
        for i, node_a in enumerate(sorted_nodes):
            la = node_a["label"].lower()
            for node_b in sorted_nodes[i + 1:]:
                lb = node_b["label"].lower()
                matched = False
                for from_kw, to_kw, rel_type, reason, confidence in _TECH_DEPS:
                    if matched:
                        break
                    if from_kw in la and to_kw in lb:
                        pair = (node_a["node_id"], node_b["node_id"])
                        if pair not in existing_pairs:
                            edge = self._make_inferred_edge(
                                node_a, node_b,
                                rel_type=rel_type, rule="tech_dependency",
                                reason=reason, confidence=confidence,
                            )
                            inferred.append(edge)
                            existing_pairs.add(pair)
                            degree[node_a["node_id"]] = degree.get(node_a["node_id"], 0) + 1
                            degree[node_b["node_id"]] = degree.get(node_b["node_id"], 0) + 1
                        matched = True
                        continue
                    if from_kw in lb and to_kw in la:
                        pair = (node_b["node_id"], node_a["node_id"])
                        if pair not in existing_pairs:
                            edge = self._make_inferred_edge(
                                node_b, node_a,
                                rel_type=rel_type, rule="tech_dependency",
                                reason=reason + " (reversed)", confidence=confidence,
                            )
                            inferred.append(edge)
                            existing_pairs.add(pair)
                            degree[node_b["node_id"]] = degree.get(node_b["node_id"], 0) + 1
                            degree[node_a["node_id"]] = degree.get(node_a["node_id"], 0) + 1
                        matched = True

        # ── Rule 3: Completion guard ─────────────────────────────────────────
        for node in sorted_nodes:
            if degree.get(node["node_id"], 0) > 0:
                continue
            zone = node.get("zone")
            anchor: Optional[Dict[str, object]] = None
            # Prefer a connected node in the same zone
            for candidate in zone_nodes.get(zone, []):
                if candidate["node_id"] != node["node_id"] and degree.get(candidate["node_id"], 0) > 0:
                    anchor = candidate
                    break
            # Fall back to any connected node globally
            if anchor is None:
                for candidate in sorted_nodes:
                    if candidate["node_id"] != node["node_id"] and degree.get(candidate["node_id"], 0) > 0:
                        anchor = candidate
                        break
            # Last resort: connect to any other node even if it too has degree 0
            if anchor is None:
                for candidate in sorted_nodes:
                    if candidate["node_id"] != node["node_id"]:
                        anchor = candidate
                        break
            if anchor is None:
                continue
            pair = (anchor["node_id"], node["node_id"])
            if pair not in existing_pairs:
                edge = self._make_inferred_edge(
                    anchor, node,
                    rel_type="async",
                    rule="completion_guard",
                    reason=f"completion guard: '{node['label']}' had no edges",
                    confidence=0.3,
                )
                inferred.append(edge)
                existing_pairs.add(pair)
                degree[anchor["node_id"]] = degree.get(anchor["node_id"], 0) + 1
                degree[node["node_id"]] = degree.get(node["node_id"], 0) + 1

        self.edges.extend(inferred)

    def _make_inferred_edge(
        self,
        from_node: Dict[str, object],
        to_node: Dict[str, object],
        rel_type: str,
        rule: str,
        reason: str,
        confidence: float,
    ) -> Dict[str, object]:
        """Build a schema-compliant inferred edge and record to self.inference_log."""
        edge_id = _unique_identifier(
            f"{from_node['node_id']}__{to_node['node_id']}__inferred",
            self.edge_ids,
            prefix="edge",
        )
        color = self.palette[1 % len(self.palette)]
        text_style: Dict[str, object] = {
            "fontSize": 11,
            "fontFamily": FONT_FAMILY,
            "textColor": color,
        }
        self.inference_log.append({
            "edge_id": edge_id,
            "from_id": from_node["node_id"],
            "to_id": to_node["node_id"],
            "rule": rule,
            "reason": reason,
            "confidence": confidence,
        })
        return {
            "edge_id": edge_id,
            "from_id": from_node["node_id"],
            "to_id": to_node["node_id"],
            "rel_type": rel_type,
            "label": reason,
            "style": "dashed",
            "color": color,
            "width": 1,
            "arrowhead": "open",
            "text_style": text_style,
            "curvature": 0.0,
            "confidence": confidence,
            "reason": reason,
        }

    def _sort_nodes(self) -> None:
        zone_rank = {zone: idx for idx, zone in enumerate(self.zone_order)}
        self.nodes.sort(key=lambda node: (zone_rank.get(node.get("zone"), len(zone_rank)), node["label"].lower()))

    def _node_intent(self) -> Dict[str, Dict[str, object]]:
        intent: Dict[str, Dict[str, object]] = {}
        for node in self.nodes:
            role = node["role"]
            if role in intent:
                continue
            entry = {
                "shape": node["shape"],
                "default_style": deepcopy(node["node_style"]),
                "stereotype": node.get("stereotype"),
            }
            intent[role] = entry
        return intent

    def _edge_intent(self) -> Dict[str, Dict[str, object]]:
        intent: Dict[str, Dict[str, object]] = {}
        for edge in self.edges:
            rel_type = edge["rel_type"]
            if rel_type in intent:
                continue
            intent[rel_type] = {
                "style": edge["style"],
                "color": edge["color"],
                "width": edge["width"],
                "arrowhead": edge["arrowhead"],
                "text_style": deepcopy(edge["text_style"]),
            }
        return intent

    def _global_intent(self) -> Dict[str, object]:
        density = self._density()
        mood = self._mood()
        return {
            "palette": self.palette,
            "layout": self.layout,
            "density": density,
            "mood": mood,
        }

    def _density(self) -> str:
        if isinstance(self.aesthetic_intent, dict):
            density = (self.aesthetic_intent.get("globalIntent") or {}).get("density")
            if isinstance(density, str):
                normalized = density.lower()
                if normalized in ALLOWED_DENSITY:
                    return normalized
        total_nodes = len(self.nodes)
        if total_nodes >= 10:
            return "compact"
        if total_nodes <= 3:
            return "spacious"
        return "balanced"

    def _mood(self) -> str:
        if isinstance(self.aesthetic_intent, dict):
            mood = (self.aesthetic_intent.get("globalIntent") or {}).get("mood")
            if isinstance(mood, str):
                normalized = mood.lower()
                if normalized in ALLOWED_MOODS:
                    return normalized
        return "minimal"

    def _metadata(self) -> Dict[str, object]:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        validation = list(self.validation_messages)
        validation.append({"severity": "info", "message": "Enriched deterministically"})
        return {
            "generated_by": "src.tools.ir_enricher",
            "spec_version": "v34",
            "timestamp": timestamp,
            "validation": validation,
            "source_system": self.source.get("system_name"),
        }

    @staticmethod
    def _rel_value(rel: object, primary: str, alternate: Optional[str] = None) -> Optional[object]:
        if isinstance(rel, dict):
            if primary in rel:
                return rel.get(primary)
            if alternate and alternate in rel:
                return rel.get(alternate)
            return None
        if hasattr(rel, primary):
            return getattr(rel, primary)
        if alternate and hasattr(rel, alternate):
            return getattr(rel, alternate)
        return None


def _label_key(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip().lower())


def _normalize_color(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    token = value.strip()
    if not token:
        return None
    if re.match(r"^#[0-9a-fA-F]{6}$", token):
        return token.upper()
    short = re.match(r"^#[0-9a-fA-F]{3}$", token)
    if short:
        expanded = "#" + "".join(ch * 2 for ch in short.group(0)[1:])
        return expanded.upper()
    rgb = re.match(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", token, re.IGNORECASE)
    if rgb:
        r, g, b = (max(0, min(255, int(part))) for part in rgb.groups())
        return f"#{r:02X}{g:02X}{b:02X}"
    return None


def _unique_identifier(label: str, existing: set[str], prefix: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or prefix
    candidate = base
    counter = 2
    while candidate in existing:
        candidate = f"{base}_{counter}"
        counter += 1
    existing.add(candidate)
    return candidate


def _role_from_label(label: str) -> str:
    lowered = label.lower()
    if any(word in lowered for word in ["user", "client", "portal", "browser", "mobile"]):
        return "actor"
    if any(word in lowered for word in ["gateway", "edge", "ingress"]):
        return "gateway"
    if any(word in lowered for word in ["db", "database", "store", "storage", "cache"]):
        return "data_store"
    if any(word in lowered for word in ["email", "sms", "auth", "payment", "third", "external"]):
        return "external"
    return "service"


def _mermaid_identifier(label: str) -> str:
    parts = re.split(r"[^a-zA-Z0-9]", label)
    cleaned = "".join(part.capitalize() for part in parts if part)
    return cleaned or "Node"


@lru_cache(maxsize=4)
def _load_schema(path: Path) -> Dict[str, object]:
    text = path.read_text(encoding="utf-8")
    return json.loads(text)
