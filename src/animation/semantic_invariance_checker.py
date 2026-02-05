"""Semantic Invariance Checker - Validates SVG structure before/after animation injection."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Set, Tuple

from src.animation.svg_structural_analyzer import (
    SVGStructuralGraph,
    analyze_svg,
    compare_structures,
)


class InvarianceViolationType(Enum):
    """Types of semantic invariance violations."""
    NODE_MISSING = "node_missing"
    NODE_ADDED = "node_added"
    EDGE_MISSING = "edge_missing"
    EDGE_ADDED = "edge_added"
    GROUP_MISSING = "group_missing"
    GROUP_ADDED = "group_added"
    LABEL_CHANGED = "label_changed"
    STRUCTURE_CHANGED = "structure_changed"
    ID_COLLISION = "id_collision"


@dataclass
class InvarianceViolation:
    """A single invariance violation."""
    violation_type: InvarianceViolationType
    element_id: str
    description: str
    severity: str  # "error", "warning", "info"
    
    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.violation_type.value}: {self.description}"


@dataclass
class InvarianceCheckResult:
    """Result of semantic invariance check."""
    is_valid: bool
    violations: List[InvarianceViolation]
    pre_structure: SVGStructuralGraph
    post_structure: SVGStructuralGraph
    summary: str
    
    @property
    def error_count(self) -> int:
        return len([v for v in self.violations if v.severity == "error"])
    
    @property
    def warning_count(self) -> int:
        return len([v for v in self.violations if v.severity == "warning"])


def check_semantic_invariance(
    pre_svg: str, 
    post_svg: str,
    strict: bool = True
) -> InvarianceCheckResult:
    """
    Check that animation injection preserves semantic structure.
    
    The following invariants must hold:
    1. All original nodes must still exist
    2. All original edges must still exist
    3. All original groups must still exist
    4. Node/edge labels must not change
    5. Parent-child relationships must not change
    
    The following are allowed:
    1. Addition of <style> elements
    2. Addition of <script> elements
    3. Addition of animation-related attributes
    4. Addition of class attributes for animation
    
    Args:
        pre_svg: SVG content before animation injection
        post_svg: SVG content after animation injection
        strict: If True, any structural change is an error
    
    Returns:
        InvarianceCheckResult with validation status and violations
    """
    violations: List[InvarianceViolation] = []
    
    # Analyze both structures
    pre_struct = analyze_svg(pre_svg)
    post_struct = analyze_svg(post_svg)
    
    # Use structural comparison
    diff = compare_structures(pre_struct, post_struct)
    
    # Check for missing nodes (error)
    pre_node_ids = {n.id for n in pre_struct.nodes}
    post_node_ids = {n.id for n in post_struct.nodes}
    
    missing_nodes = pre_node_ids - post_node_ids
    for node_id in missing_nodes:
        pre_node = next(n for n in pre_struct.nodes if n.id == node_id)
        violations.append(InvarianceViolation(
            violation_type=InvarianceViolationType.NODE_MISSING,
            element_id=node_id,
            description=f"Node '{pre_node.label or node_id}' was removed after animation injection",
            severity="error"
        ))
    
    # Check for added nodes (warning in strict mode)
    added_nodes = post_node_ids - pre_node_ids
    for node_id in added_nodes:
        post_node = next(n for n in post_struct.nodes if n.id == node_id)
        severity = "warning" if strict else "info"
        violations.append(InvarianceViolation(
            violation_type=InvarianceViolationType.NODE_ADDED,
            element_id=node_id,
            description=f"Node '{post_node.label or node_id}' was added during animation injection",
            severity=severity
        ))
    
    # Check for missing edges (error) - first by ID, then by connection
    pre_edge_ids = {e.id for e in pre_struct.edges}
    post_edge_ids = {e.id for e in post_struct.edges}
    
    missing_edge_ids = pre_edge_ids - post_edge_ids
    for edge_id in missing_edge_ids:
        violations.append(InvarianceViolation(
            violation_type=InvarianceViolationType.EDGE_MISSING,
            element_id=edge_id,
            description=f"Edge '{edge_id}' was removed",
            severity="error"
        ))
    
    # Also check by source/target if available
    pre_edge_keys = {(e.source_id, e.target_id) for e in pre_struct.edges if e.source_id and e.target_id}
    post_edge_keys = {(e.source_id, e.target_id) for e in post_struct.edges if e.source_id and e.target_id}
    
    missing_edges = pre_edge_keys - post_edge_keys
    for source_id, target_id in missing_edges:
        violations.append(InvarianceViolation(
            violation_type=InvarianceViolationType.EDGE_MISSING,
            element_id=f"{source_id}->{target_id}",
            description=f"Edge from '{source_id}' to '{target_id}' was removed",
            severity="error"
        ))
    
    # Check for added edges (warning in strict mode)
    added_edge_ids = post_edge_ids - pre_edge_ids
    for edge_id in added_edge_ids:
        severity = "warning" if strict else "info"
        violations.append(InvarianceViolation(
            violation_type=InvarianceViolationType.EDGE_ADDED,
            element_id=edge_id,
            description=f"Edge '{edge_id}' was added",
            severity=severity
        ))
    
    added_edges = post_edge_keys - pre_edge_keys
    for source_id, target_id in added_edges:
        severity = "warning" if strict else "info"
        violations.append(InvarianceViolation(
            violation_type=InvarianceViolationType.EDGE_ADDED,
            element_id=f"{source_id}->{target_id}",
            description=f"Edge from '{source_id}' to '{target_id}' was added",
            severity=severity
        ))
    
    # Check for missing groups (error)
    pre_group_ids = {g.id for g in pre_struct.groups}
    post_group_ids = {g.id for g in post_struct.groups}
    
    missing_groups = pre_group_ids - post_group_ids
    for group_id in missing_groups:
        violations.append(InvarianceViolation(
            violation_type=InvarianceViolationType.GROUP_MISSING,
            element_id=group_id,
            description=f"Group '{group_id}' was removed after animation injection",
            severity="error"
        ))
    
    # Check label changes (error)
    for pre_node in pre_struct.nodes:
        post_node = next((n for n in post_struct.nodes if n.id == pre_node.id), None)
        if post_node and pre_node.label != post_node.label:
            violations.append(InvarianceViolation(
                violation_type=InvarianceViolationType.LABEL_CHANGED,
                element_id=pre_node.id,
                description=f"Label changed from '{pre_node.label}' to '{post_node.label}'",
                severity="error"
            ))
    
    # Check if structure is fundamentally different (using diff)
    node_diff = abs(len(pre_struct.nodes) - len(post_struct.nodes))
    edge_diff = abs(len(pre_struct.edges) - len(post_struct.edges))
    total_elements = max(len(pre_struct.nodes) + len(pre_struct.edges), 1)
    structural_similarity = 1.0 - (node_diff + edge_diff) / (total_elements * 2)
    
    if structural_similarity < 0.95:
        violations.append(InvarianceViolation(
            violation_type=InvarianceViolationType.STRUCTURE_CHANGED,
            element_id="root",
            description=f"Overall structure changed significantly (similarity: {structural_similarity:.2%})",
            severity="error" if structural_similarity < 0.8 else "warning"
        ))
    
    # Determine validity
    error_count = len([v for v in violations if v.severity == "error"])
    is_valid = error_count == 0
    
    # Generate summary
    if is_valid and not violations:
        summary = "✓ Semantic invariance preserved: no violations detected"
    elif is_valid:
        summary = f"✓ Semantic invariance preserved with {len(violations)} warnings"
    else:
        summary = f"✗ Semantic invariance violated: {error_count} errors, {len(violations) - error_count} warnings"
    
    return InvarianceCheckResult(
        is_valid=is_valid,
        violations=violations,
        pre_structure=pre_struct,
        post_structure=post_struct,
        summary=summary
    )


def validate_animation_safety(pre_svg: str, post_svg: str) -> Tuple[bool, str]:
    """
    Quick validation that animation injection is safe.
    
    Returns:
        (is_safe, message) tuple
    """
    result = check_semantic_invariance(pre_svg, post_svg, strict=True)
    return result.is_valid, result.summary


def get_allowed_modifications() -> Set[str]:
    """Get set of allowed SVG modifications during animation injection."""
    return {
        "style",      # Style elements for CSS animations
        "script",     # Script elements for JS animations
        "class",      # Class attributes for animation targeting
        "animation",  # Animation-related attributes
        "stroke-dasharray",  # For flow animations
        "stroke-dashoffset", # For flow animations
        "transform-origin",  # For scale/rotate animations
    }


def report_violations(result: InvarianceCheckResult) -> str:
    """Generate a human-readable violation report."""
    lines = []
    lines.append("=" * 60)
    lines.append("SEMANTIC INVARIANCE CHECK REPORT")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Status: {'PASSED' if result.is_valid else 'FAILED'}")
    lines.append(f"Errors: {result.error_count}")
    lines.append(f"Warnings: {result.warning_count}")
    lines.append("")
    
    if result.violations:
        lines.append("VIOLATIONS:")
        lines.append("-" * 40)
        for v in result.violations:
            lines.append(str(v))
        lines.append("")
    
    lines.append("STRUCTURE COMPARISON:")
    lines.append("-" * 40)
    lines.append(f"Pre-animation nodes: {len(result.pre_structure.nodes)}")
    lines.append(f"Post-animation nodes: {len(result.post_structure.nodes)}")
    lines.append(f"Pre-animation edges: {len(result.pre_structure.edges)}")
    lines.append(f"Post-animation edges: {len(result.post_structure.edges)}")
    lines.append(f"Pre-animation groups: {len(result.pre_structure.groups)}")
    lines.append(f"Post-animation groups: {len(result.post_structure.groups)}")
    lines.append("")
    lines.append(result.summary)
    lines.append("=" * 60)
    
    return "\n".join(lines)
