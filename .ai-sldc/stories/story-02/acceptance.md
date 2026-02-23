# Story-02 Acceptance Criteria

Minimum acceptance for `story-02`:

1. A draft plan `.ai-sldc/plans/PLAN-story-02.draft.md` is present and describes the proposed fix, scope, tests, risks, and rollback strategy.
2. Repository state updated to show `phase: awaiting_approval` in `.ai-sldc/state.json`.
3. An entry is appended to `.ai-sldc/logs/execution.log` recording `PLAN_CREATED` for `story-02`.
4. All changes are limited to `.ai-sldc/*` (planning artifacts) during this planning invocation.

Notes:
- Implementation, tests, and commits to source code will happen only after plan approval.
# Acceptance Criteria: Diagram Quality Improvement

## Functional Acceptance

### 1. Data Collection
- [ ] ~100 diagram image URLs collected
- [ ] Metadata stored locally (JSON)
- [ ] No copyrighted asset redistribution

### 2. Pattern Extraction Report
- [ ] Icon usage summary
- [ ] Color pattern summary
- [ ] Structural layout summary
- [ ] Annotation summary
- [ ] Boundary & separation patterns

### 3. Deterministic Style Rules

Generated `style_rules.json` containing:

{
  "icon_policy": {...},
  "color_palette": {...},
  "layering_rules": {...},
  "annotation_rules": {...},
  "boundary_rules": {...}
}

### 4. Rendering Engine Update

- [ ] IR → SVG respects new style rules
- [ ] Icons can be injected
- [ ] Boundaries rendered as containers
- [ ] Header block supported
- [ ] Legend block supported
- [ ] Color palette applied by node type

### 5. Regression Test

Generate 3 diagrams:
- Simple 3-tier architecture
- Microservices architecture
- Data pipeline architecture

Compare:

| Metric | Before | After |
|--------|--------|-------|
| Visual clarity | Low | High |
| Grouping clarity | Weak | Strong |
| Icon support | No | Yes |
| Layer hierarchy | Flat | Structured |
| Annotation quality | Minimal | Informative |

---

## Quality Acceptance

- No hard-coded styles
- All styling controlled via style_rules.json
- Deterministic output
- Zero random styling decisions

---

## Test Cases

### Test 1: Icon Injection
Input IR with type=database  
Expected: Database icon rendered

### Test 2: Layer Grouping
Input IR with logical groups  
Expected: Boundary container drawn

### Test 3: Header Rendering
Input includes diagram.title  
Expected: Header rendered at top

### Test 4: Legend Rendering
If legend enabled  
Expected: Legend box generated

### Test 5: Color Policy
Node types → consistent colors