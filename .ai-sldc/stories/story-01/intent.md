# Story 01 — Improve icon rendering stability

Intent:

Stabilize and improve the icon-renderer used by the `icons` worktree so that exported SVG/PNG assets are consistent across runs and do not drop metadata. This is a small feature scoped to the renderer module and associated export pipeline.

Goals:
- Reproduce current intermittent rendering artifact locally.
- Propose minimal, deterministic fix scoped to renderer configuration or asset export logic.
- Provide acceptance criteria and tests that guard regression.
# STORY-ICON-001
## Title
Embed Service Icons in Diagram Agent Output

## Background

The diagram generation agent currently renders services (e.g., Postgres, Kafka, MinIO) without brand/service icons. 
This reduces visual clarity and professional quality of diagrams.

We want the system to embed appropriate service icons into rendered SVG output in a deterministic and testable manner.

## Objective

Enable the diagram agent to:
- Detect known services (e.g., postgres, kafka, minio)
- Inject corresponding SVG icons
- Ensure icons render correctly in UI
- Ensure feature works in headless Cypress environment

## Scope

In Scope:
- SVG inline icon embedding
- Support for at least:
  - postgres
  - kafka
  - minio
- Deterministic mapping between service type and icon
- Cypress test coverage

Out of Scope:
- Dynamic icon downloading from internet
- Runtime CDN dependencies
- GIF conversion

## Constraints

- Must work offline
- Must not break existing diagram generation
- Must preserve SVG validity
- Must not degrade performance significantly

## Non-Functional Expectations

- Deterministic output
- No random injection
- Icons must not overlap labels
- Must degrade gracefully if icon missing