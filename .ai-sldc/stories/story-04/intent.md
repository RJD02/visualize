# STORY-DIAGRAM-COHESION-01
# Enhance Diagram Agent: Reduce Isolated Nodes, Improve Connectivity, Cohesive Architecture Output

## Objective

Improve the diagram agent so generated architecture diagrams:
- have fewer isolated/unconnected nodes
- show meaningful connectivity between components
- represent the system as a cohesive architecture (not scattered blocks)

This is an **agent quality and layout/graph construction improvement** story.

---

## Problem Statement

Current outputs often contain:
- isolated blocks with no edges
- partial subgraphs instead of a unified architecture
- missing relationship inference (components that should be connected are disconnected)
- low “storytelling” value in the architecture (viewer cannot understand flow)

This reduces clarity and makes the output look incomplete.

---

## Scope

1) **Connectivity Inference Improvements**
   - Infer relationships from:
     - common naming patterns (e.g., “DC Object Store” ↔ “DR Object Store”)
     - layer conventions (users → ingress → auth → services → storage)
     - known tech dependencies (e.g., services → DB/object store, Kafka producers/consumers)
   - Add “weak links” when information is insufficient but relationship is likely, marked visually (dashed/optional).

2) **Graph Completion**
   - Ensure all recognized components appear in a single diagram graph.
   - Avoid generating disconnected islands unless explicitly requested (e.g., “show only storage layer”).

3) **Layout Cohesion**
   - Prefer layered or grouped layout:
     - Users / Clients
     - Edge / Ingress
     - Auth / Security
     - Runtime / Compute
     - Data / Storage
     - Observability
   - Reduce excessive whitespace and scattered nodes.

4) **Explainability**
   - When the agent creates inferred edges, it must emit a structured explanation (in a log artifact) that lists:
     - inferred edge
     - reason / rule used
     - confidence score

5) **Determinism**
   - Given same IR/input, produced diagram should be stable (no random linking).
   - Use deterministic rules and stable sorting.

---

## Non-Goals

- Not redesigning the entire IR schema.
- Not implementing interactive graph editing.
- Not generating multiple alternative diagrams in this story.
- Not adding new icon sets (separate story/bug).

---

## Testing Strategy

- Unit tests for:
  - relationship inference rules (given input nodes, expected edges produced)
  - deterministic ordering and stable output

- Playwright/Cypress:
  - generate a representative architecture diagram
  - validate:
    - edge count is above a minimum threshold
    - % isolated nodes is below a threshold
    - screenshot evidence exists

---

## Success Definition

- Isolated node ratio drops significantly (target defined in acceptance).
- Diagrams show end-to-end flow with clear connections.
- Inferred edges are explainable and deterministic.
- UI visual evidence confirms cohesion improvement.