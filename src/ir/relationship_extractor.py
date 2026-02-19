"""Deterministic relationship extraction engine for IR, per specs_v43."""
import re
import uuid
from typing import List, Dict, Any
from src.ir_v2 import Edge, make_edge_id

# Mapping of verbs/phrases to (relation_type, category, mode, label, direction)
_RELATION_PATTERNS = [
    (r"connect[s]?", ("connect", "user_traffic", "sync", None, "unidirectional")),
    (r"replicat(e|es|es to|es into|es from|es between|es across|es with|es on|es in|es out)?|mirror[s]?", ("replicate", "replication", "async", None, "unidirectional")),
    (r"suppl(y|ies|ies secrets|ies credentials|ies tokens|ies keys)?|inject[s]?|provide[s]? secrets", ("supply_secrets", "secret_distribution", "broadcast", None, "unidirectional")),
    (r"write[s]?|produce[s]?", ("write", "data_flow", "sync", None, "unidirectional")),
    (r"read[s]?|quer(y|ies)", ("read", "data_flow", "sync", None, "unidirectional")),
    (r"authenticat(e|es|ion|es with|es to|es via|es against)?|SSO", ("auth", "auth", "sync", None, "unidirectional")),
    (r"monitor[s]?|collect[s]? metrics", ("monitor", "monitoring", "sync", None, "unidirectional")),
    (r"feed[s]?", ("feed", "data_flow", "sync", None, "unidirectional")),
    (r"publish(es)?|consume(s)?", ("pubsub", "data_flow", "async", None, "unidirectional")),
    (r"failover|promote", ("control", "control", "sync", None, "unidirectional")),
]

# Helper to expand multi-targets (e.g., "all services")
def _expand_targets(target: str, blocks: List[Dict[str, Any]]) -> List[str]:
    if target.lower() in ("all", "all services", "all components", "all nodes"):
        return [b["id"] for b in blocks]
    return [target]

# Main extraction function
def extract_relationships(prompt: str, blocks: List[Dict[str, Any]], *, max_edges_per_node: int = 5, enforce_gateway: bool = True) -> List[Edge]:
    """Extract relationships and apply normalization rules to avoid N×M edges.

    - Detect relations via simple pattern matching.
    - Expand multi-targets like "all services".
    - Collapse long lists of outgoing edges from external actors into
      cluster-level edges (edge-reduction).
    - Optionally enforce gateway routing: route external->internal via an ingress node.
    """
    edges: List[Edge] = []
    prompt_lc = prompt.lower()
    block_ids = [b["id"] for b in blocks]

    # First-pass: naive extraction as before
    raw_edges: List[Edge] = []
    for pat, (relation_type, category, mode, label, direction) in _RELATION_PATTERNS:
        for m in re.finditer(pat, prompt_lc):
            after = prompt_lc[m.end():]
            before = prompt_lc[:m.start()]
            src_match = re.search(r"([A-Za-z0-9_\- ]+)$", before)
            src = src_match.group(1).strip() if src_match else None
            tgt_match = re.search(r"to ([A-Za-z0-9_\- ]+|all services|all components|all nodes)", after)
            tgt = tgt_match.group(1).strip() if tgt_match else None
            # Fallback: handle verb-first prompts like "Connect A to B"
            if not src or not tgt:
                m2 = re.search(r"([A-Za-z0-9_\- ]+) to ([A-Za-z0-9_\- ]+)", prompt_lc)
                if m2:
                    src_cand = src or m2.group(1).strip()
                    tgt_cand = tgt or m2.group(2).strip()
                    # Strip leading verb (e.g., 'connect a') if present
                    if src_cand and src_cand.startswith(relation_type):
                        src_cand = src_cand[len(relation_type):].strip()
                    # Map to existing block ids by case-insensitive match if possible
                    src = None
                    tgt = None
                    for b in block_ids:
                        if src_cand and b.lower() == src_cand.lower():
                            src = b
                        if tgt_cand and b.lower() == tgt_cand.lower():
                            tgt = b
                    # Fallback to raw candidates if mapping failed
                    src = src or src_cand
                    tgt = tgt or tgt_cand

            if src and tgt:
                # Map extracted names to canonical block ids (preserve casing)
                src = next((b for b in block_ids if b.lower() == src.lower()), src)
                targets = _expand_targets(tgt, blocks)
                # map targets similarly
                mapped_targets = []
                for t in targets:
                    mapped_targets.append(next((b for b in block_ids if b.lower() == t.lower()), t))
                targets = mapped_targets
                # remove self-targets (e.g., 'all services' should exclude the source)
                targets = [t for t in targets if t.lower() != src.lower()]
                for t in targets:
                    e = Edge(
                        edge_id=make_edge_id(),
                        from_=src,
                        to=t,
                        relation_type=relation_type,
                        direction=direction,
                        category=category,
                        mode=mode,
                        label=label or f"{relation_type}",
                        confidence=1.0 if src in block_ids and t in block_ids else 0.6,
                    )
                    raw_edges.append(e)

    if not raw_edges:
        return []

    # Group edges by source
    by_source: Dict[str, List[Edge]] = {}
    for e in raw_edges:
        by_source.setdefault(e.from_, []).append(e)

    # Helper to detect cluster-like targets (heuristic)
    def _cluster_of(target: str) -> str | None:
        lowered = target.lower()
        for kw in ("cluster", "pool", "k8s", "kubernetes", "spark", "trino", "platform", "storage", "service"):
            if kw in lowered:
                return lowered
        return None

    # Apply reduction rules per source
    for src, outs in by_source.items():
        if len(outs) <= max_edges_per_node:
            edges.extend(outs)
            continue

        # If too many outgoing edges, attempt to reduce by grouping targets by cluster
        clusters: Dict[str, List[Edge]] = {}
        others: List[Edge] = []
        for e in outs:
            c = _cluster_of(e.to)
            if c:
                clusters.setdefault(c, []).append(e)
            else:
                others.append(e)

        # Create cluster-level edges for clusters with multiple targets
        for cluster_name, cluster_edges in clusters.items():
            # Prefer a well-known ingress name if enforcing gateway routing
            if enforce_gateway:
                ingress_id = f"ingress_{cluster_name}"
                new_edge = Edge(edge_id=make_edge_id(), from_=src, to=ingress_id, relation_type="routes_to", direction="unidirectional", category="user_traffic", mode="sync", label="routes_to", confidence=0.9)
                edges.append(new_edge)
                # Optionally create internal cluster->component edges (preserve semantic)
                for ce in cluster_edges:
                    internal_edge = Edge(edge_id=make_edge_id(), from_=cluster_name, to=ce.to, relation_type=ce.relation_type, direction=ce.direction, category=ce.category, mode=ce.mode, label=ce.label, confidence=ce.confidence * 0.9)
                    edges.append(internal_edge)
            else:
                # Collapse into a single cluster edge
                cluster_id = f"cluster_{cluster_name}"
                new_edge = Edge(edge_id=make_edge_id(), from_=src, to=cluster_id, relation_type="routes_to", direction="unidirectional", category="user_traffic", mode="sync", label="routes_to", confidence=0.8)
                edges.append(new_edge)

        # Keep other edges but enforce an upper bound
        remaining = others
        if len(remaining) > max_edges_per_node:
            # collapse remaining into a group node
            group_id = f"group_targets_{src}".replace(" ", "_")
            edges.append(Edge(edge_id=make_edge_id(), from_=src, to=group_id, relation_type="routes_to", direction="unidirectional", category="user_traffic", mode="sync", label="routes_to", confidence=0.75))
        else:
            edges.extend(remaining)

    # Deduplicate edges by (from,to,label)
    seen = set()
    deduped: List[Edge] = []
    for e in edges:
        key = (e.from_, e.to, e.label)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)

    return deduped
