# STORY-DIAGRAM-COHESION-01
# Acceptance Criteria

## Connectivity Quality

[ ] For standard “infra architecture” prompts, diagram contains meaningful edges (not just blocks).
[ ] Isolated nodes reduced:
    - isolated_nodes / total_nodes <= 0.15 (15%) for reference test prompt(s)
[ ] Minimum connectivity baseline:
    - total_edges >= max( total_nodes - 1, 10 ) for reference test prompt(s)
[ ] Agent creates inferred edges only via deterministic rules.

## Cohesive Architecture Representation

[ ] All recognized components appear in one coherent graph (no unnecessary islands).
[ ] Layers/groups exist (users/edge/auth/runtime/data/observability or equivalent).
[ ] Viewer can trace at least one “happy path” flow from users → ingress → services → data.

## Explainability & Audit

[ ] For each inferred edge, an explanation record is generated containing:
    - from_node, to_node
    - rule applied
    - reason
    - confidence score
[ ] Explanations accessible in-memory via _IREnricher.inference_log (list of {rule, reason, confidence} dicts); not written to disk artifact.

## Determinism

[ ] Same input yields same node order and edge set.
[ ] No random linking or nondeterministic ordering.

## Tests & Evidence

[ ] Unit tests pass.
[ ] Playwright/Cypress headless runs and produces screenshot evidence.
[ ] Evidence includes:
    - diagram screenshot
    - metrics output (nodes, edges, isolated count)
[ ] PR review yields zero open feedback.
[ ] Confidence score ≥ 0.85.