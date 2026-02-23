# PLAN-STORY-DIAGRAM-COHESION-01
# Draft Plan — Enhance Diagram Agent: Reduce Isolated Nodes, Improve Connectivity

**Entity ID:** STORY-DIAGRAM-COHESION-01
**Kind:** feature
**Branch:** feature/STORY-DIAGRAM-COHESION-01
**Plan ID:** PLAN-STORY-DIAGRAM-COHESION-01

---

## 1. Problem Understanding

Diagrams are generated with too many isolated nodes and too few meaningful edges.
The visual result is a scattered set of unconnected blocks rather than a cohesive
architecture.

---

## 2. Architectural Root Cause

The pipeline today is:

```
architect_agent
  → ArchitecturePlan { zones, relationships }
      → diagram_agent
          → generate_plantuml_from_plan()   ← renderer
```

**The `ir_enricher.py` module is skipped entirely.**
`diagram_agent.py` calls `generate_plantuml_from_plan(plan)` directly, bypassing
the existing `enrich_ir()` step.

Even if the enricher were called, it does not infer missing relationships — it only
propagates what the LLM produced.  When the LLM emits a sparse `relationships` list,
every renderer (PlantUML, Mermaid, future ones) sees the same underspecified IR and
produces the same disconnected diagram.

**This is an IR-quality problem, not a renderer problem.**
The renderer faithfully draws what it is given.  Adding connectivity logic inside
`plantuml_renderer.py` would:
- Silently duplicate logic for every renderer
- Leave Mermaid / Structurizr diagrams broken
- Violate separation of concerns

The correct fix is to enrich the IR *before any renderer sees it*.

---

## 3. Correct Architectural Fix

### 3a. Extend `ir_enricher.py` with connectivity inference

Add a `_infer_missing_connections()` method to `_IREnricher`.
It runs as the final step inside `build()`, after `_populate_edges()`.

**Inference rules (deterministic, ordered):**

**Rule 1 — Zone-layer cascade (weak, dashed)**
For each adjacent pair in `zone_order` (clients→edge, edge→core_services,
core_services→data_stores, external_services→core_services), if no explicit
edge already connects ANY node from zone A to ANY node in zone B:
- Take the FIRST (sorted) node in zone A as `from`
- Take the FIRST (sorted) node in zone B as `to`
- Infer a `rel_type="async"` edge with `style="dashed"`, `confidence=0.5`

**Rule 2 — Tech-dependency keywords (medium, dashed)**
Known dependency pairs detected via label substring match (case-insensitive):

| If label contains | And other label contains | Infer |
|-------------------|--------------------------|-------|
| kafka / streaming | consumer / processor / worker | async |
| kafka / streaming | producer / publisher | async (reversed) |
| prometheus / metrics | grafana / dashboard | data |
| airflow / scheduler | spark / worker | async |
| ingress / gateway | any core_service node | sync |
| any core_service | postgres / mysql / mongo / redis | data |
| dc object / primary | dr object / replica / secondary | data |

**Rule 3 — Completion guard**
After Rules 1 and 2, if any node has degree 0 (no edges at all), add a weak
dashed edge from its zone's anchor node (first in zone by label sort) to it.
Prevents any node from being a complete island.

### 3b. Add explainability to enriched IR

Each inferred edge produced by Rules 1-3 includes in its `metadata`:
```json
{
  "inferred": true,
  "rule": "zone_cascade | tech_dependency | completion_guard",
  "reason": "human-readable string",
  "confidence": 0.3 | 0.5 | 0.7
}
```
All inferred edges are also written to a structured log artifact under
`.ai-sldc/stories/story-04/evidence/inference_log.json`.

### 3c. Wire the enricher into `diagram_agent.py`

`diagram_agent.py` currently skips enrichment.  Fix:

```python
# Before (broken):
plan = ArchitecturePlan.model_validate(plan_state)
diagrams = generate_plantuml_from_plan(plan)

# After (correct):
plan = ArchitecturePlan.model_validate(plan_state)
enriched = enrich_ir(plan.model_dump(by_alias=True))   # now includes inferred edges
plan = _merge_inferred_edges(plan, enriched["edges"])  # write back to ArchitecturePlan
diagrams = generate_plantuml_from_plan(plan)           # renderer sees complete IR
```

`_merge_inferred_edges()` is a small helper that converts enriched IR edge dicts
back to `Relationship` objects and appends them (with `type="async"` for dashed
inferred edges) to `plan.relationships`, deduplicating against existing ones.

### 3d. Determinism fix

`_IREnricher._populate_nodes()` and zone iterations already use `zone_order`.
Ensure all label sorts in the new `_infer_missing_connections()` use
`sorted(items, key=str.lower)` — no set iteration, no dict-order dependence.

---

## 4. File-Level Change Scope

### MODIFIED files

| File | Change |
|------|--------|
| `src/tools/ir_enricher.py` | Add `_infer_missing_connections()` method to `_IREnricher`; call it in `build()` |
| `src/agents/diagram_agent.py` | Call `enrich_ir()` before rendering; merge inferred edges back to plan |

### NEW files

| File | Purpose |
|------|---------|
| `tests/unit/test_connectivity_inferencer.py` | 8 unit tests against `_IREnricher` inference (see §5) |
| `tests/e2e/story04_diagram_cohesion.spec.js` | Playwright E2E: validates edge count and isolated-node ratio |

### NOT touched

| File | Why |
|------|-----|
| `src/tools/plantuml_renderer.py` | Renderer stays clean — it receives a complete IR |
| `src/tools/mermaid_renderer.py` | Same: benefits automatically once IR is enriched |
| `src/models/architecture_plan.py` | `ArchitecturePlan` schema unchanged |

### SDLC artifacts

| Path | Type |
|------|------|
| `.ai-sldc/stories/story-04/plans/PLAN-STORY-DIAGRAM-COHESION-01.draft.md` | This file |
| `.ai-sldc/stories/story-04/plans/PLAN-STORY-DIAGRAM-COHESION-01.locked.json` | On approval |
| `.ai-sldc/stories/story-04/logs/planning.log` | Phase log |

---

## 5. Test Plan

### Unit Tests (`tests/unit/test_connectivity_inferencer.py`)

Tests drive `_IREnricher` directly (or `enrich_ir()`) with crafted inputs.

| Test | Input | Expected |
|------|-------|---------|
| `test_zone_cascade_adds_edges_when_none_exist` | Nodes in clients+edge+core+data, `relationships=[]` | edges bridge each adjacent zone pair |
| `test_isolated_ratio_below_threshold` | 10 nodes, 0 explicit relationships | isolated_after / total <= 0.15 |
| `test_minimum_edge_count_met` | 12 nodes, 0 explicit relationships | `len(edges) >= max(11, 10)` |
| `test_determinism_same_input_same_output` | Same IR dict twice | identical `edges` list |
| `test_no_duplicate_edge_when_explicit_exists` | Explicit clients→edge relationship | no second clients→edge inferred edge |
| `test_explainability_record_structure` | Any inference run | each inferred edge has `metadata.rule`, `metadata.reason`, `metadata.confidence` |
| `test_tech_dependency_kafka_to_processor` | Kafka in edge zone, Event Processor in core | async edge inferred |
| `test_completion_guard_removes_all_isolated` | 1 node with no zone neighbours | guard adds 1 weak edge, isolated count = 0 |

### E2E Test (`tests/e2e/story04_diagram_cohesion.spec.js`)

```
1. Navigate to http://localhost:3000
2. Send reference prompt: "microservices platform with Kafka, Postgres,
   API Gateway, Auth Service, Prometheus and Grafana"
3. Wait for diagram (selector: [data-cy="inline-diagram"])
4. Read metrics via window.__diagramMetrics (exposed by diagram_agent)
5. Assert: total_edges >= Math.max(total_nodes - 1, 10)
6. Assert: isolated_nodes / total_nodes <= 0.15
7. Assert: at least one path exists from a "clients" zone node to a "data_stores" zone node
8. Screenshot: STORY-DIAGRAM-COHESION-01-cohesion-<timestamp>.png
9. Save run-meta.json to evidence/ui/
```

---

## 6. Acceptance Criteria Cross-Check

| Criterion | Implementation |
|-----------|---------------|
| `isolated_nodes / total_nodes <= 0.15` | Rule 1+2+3 in enricher + unit test |
| `total_edges >= max(total_nodes - 1, 10)` | Enforced by rules + unit test |
| Inferred edges only via deterministic rules | Code-defined rules, no RNG |
| All components in one coherent graph | Completion guard (Rule 3) |
| Layers/groups visible | Existing zone rendering (renderer unchanged) |
| Happy path traceable | Zone cascade guarantees clients→…→data path |
| Explainability records emitted | `metadata` on each inferred edge |
| Determinism | `sorted()` everywhere in inference; unit test |
| Mermaid diagrams also benefit | Yes — enricher runs before any renderer |
| Unit tests pass | 8 tests |
| Playwright evidence | Screenshot + metrics in evidence/ui/ |
| Confidence score ≥ 0.85 | Review gate |

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Inferred edge is wrong for an unusual architecture | `style="dashed"`, low confidence clearly communicated; easy to spot |
| `enrich_ir()` call in diagram_agent adds latency | Pure in-memory Python; no I/O during inference; negligible |
| Merge back to ArchitecturePlan loses enriched metadata | Metadata retained in enriched IR log artifact separately |
| Existing tests break if enricher changes behavior | Existing `test_ir_enricher.py` guards the enricher contract; new tests additive |

---

## 8. Rollback Strategy

- Remove the `enrich_ir()` call in `diagram_agent.py` → reverts to current behavior.
- Revert the `_infer_missing_connections()` addition to `ir_enricher.py`.
- No schema changes; no database migrations; no renderer changes.

---

## 9. Out of Scope

- Redesigning the IR schema or `ArchitecturePlan` model.
- Interactive graph editing.
- New icon sets.
- Multiple alternative diagrams per prompt.
- Changing the renderer selection logic.
