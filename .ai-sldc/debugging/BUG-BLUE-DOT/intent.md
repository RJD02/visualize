# BUG-BLUE-DOT
# Icons Render as Blue Circles/Dots Instead of Real Brand SVG Logos

## Problem

When architecture diagrams are generated and rendered in the browser, technology
icons (e.g., for Kafka, Postgres, Kubernetes) appear as **blue filled circles/dots**
instead of recognizable brand SVG logos.

Screenshot evidence: `bug_evidence/evidence_1.png`, `bug_evidence/evidence_2.png`

---

## Expected Behavior

- Nodes labeled with known technologies show the correct brand/recognizable icon.
- Icons should be visually distinct shapes (not generic circles).
- Unknown services should show a neutral placeholder, not a blue filled circle.

---

## Root Causes Identified

### Server-side (Python — `src/diagram/icon_injector.py`)

The generic fallback symbol uses a circular SVG path:

```python
_GENERIC_SYMBOL_PATH = "M12 2a10 10 0 100 20A10 10 0 0012 2zm0 2a8 8 0 110 16A8 8 0 0112 4z"
```

Combined with the CSS rule `.node-icon.generic-icon { fill: #1e40af }`, this
renders as a **blue circle** for any unresolved icon key.

When `resolve_icon_key(label)` returns `None` (keyword not matched), or when the
icon file is missing from `src/icons/`, the fallback circle is used.

### Client-side (JavaScript — `ui/src/diagram/iconRegistry.js`)

The `ICONS` map uses simple geometric SVG paths. Some entries closely resemble
circles:

```js
kafka: { path: 'M4 12a8 8 0 1116 0 8 8 0 01-16 0zm2 0h12' }  // near-circle
airflow: { path: 'M2 12c0-5 4-9 9-9s9 4 9 9-4 9-9 9S2 17 2 12z' }  // circle
```

These produce blue dot-like shapes when filled with `#1e40af`.

---

## Fix Applied

Commit `ef3e544`: "fix(icons): brand icons render as real SVG logos not blue circles"

The fix addressed server-side icon file resolution so that real SVG brand assets
are injected instead of the generic circle fallback.

This plan covers:
1. Verifying the fix is complete and working
2. Writing regression tests to prevent recurrence
3. Completing SDLC artifacts for this bug

---

## Constraints

- Must not break existing icon injection for supported services.
- Must remain deterministic: same SVG input -> same icon output.
- Must not fetch icons from external CDNs at runtime.
