You are an autonomous code agent. Your job is to: (1) set up and run this repo’s full verification/tests, (2) generate an Intermediate Representation (IR) of the system from code + specs, (3) generate final diagram images from the IR, and (4) reconcile generated outputs with expected artifacts in the repo, producing a clear pass/fail report.

Repository:
- https://github.com/rishianshu/jira_plus_plus (main branch)

Hard requirements:
- Do NOT ask me questions unless absolutely blocking; make sensible defaults.
- Prefer reproducible, scriptable steps.
- Produce all outputs under: .artifacts/ai-generated/<UTC_TIMESTAMP>/
- Everything must be runnable locally via a single command you provide at the end.
- If something is missing (e.g., Temporal server), use the repo’s recommended local substitute and document it.
- If any step fails, capture logs and still generate partial outputs + a failure summary.

0) Environment assumptions & setup
- Target Node.js 20+ and pnpm 10+.
- Use Docker for Postgres.
- Use temporalite for local Temporal (ephemeral) if Temporal isn’t running.
- Create an execution log at .artifacts/ai-generated/<TS>/run.log capturing every command and its output.

1) Clone & bootstrap
- git clone the repo
- pnpm install at repo root
- Copy env files:
  - cp .env.example .env
  - cp apps/api/.env.example apps/api/.env
  - cp apps/jira-plus-plus/.env.example apps/jira-plus-plus/.env
- Start Postgres:
  - docker compose up -d postgres
- Prisma setup:
  - pnpm --filter @jira-plus-plus/api prisma generate
  - pnpm --filter @jira-plus-plus/api prisma migrate dev --name init
- Start Temporal:
  - if TEMPORAL_ADDRESS not reachable, run: temporalite start --ephemeral (in background) and export TEMPORAL_ADDRESS appropriately.
- Start worker (background):
  - pnpm --filter @jira-plus-plus/api temporal:worker
- Run repo verification:
  - pnpm verify (preferred)
  - If verify doesn’t exist, fall back to: pnpm test, pnpm lint, pnpm typecheck (in that order)
- Save test/verify outputs to:
  - .artifacts/ai-generated/<TS>/verification/{verify.log,test.log,lint.log,typecheck.log}
- Record pass/fail of each check.

2) Generate IR (Intermediate Representation)
Create a machine-readable IR file:
- .artifacts/ai-generated/<TS>/ir/system.ir.json
- .artifacts/ai-generated/<TS>/ir/system.ir.md

IR scope:
- Monorepo structure: apps/api, apps/jira-plus-plus, packages/*, platform/*, infra/*, specs/*, tests/*
- Runtime architecture: API (Apollo GraphQL + Prisma), Web (React+Vite), DB (Postgres), Temporal worker, any ingestion pipeline (platform/spark-ingestion), test frameworks (Playwright/Cypress), and deployment/runtime hints from Dockerfiles and compose.
- Key domain flows inferred from specs/ (if present) and code:
  - user/auth/admin flows
  - Jira integration/sync flow (even if stubbed)
  - GraphQL request lifecycle
  - Background jobs / workflows via Temporal
- For each component include:
  - name, type, location (path), responsibilities
  - inputs/outputs (APIs, queues, DB tables if discernible)
  - dependencies (internal + external)
  - configuration/env vars used (from .env examples)
- Include a “confidence” field per inferred item: high/medium/low.

How to derive IR:
- Parse README, docs/, specs/ first.
- Then inspect key folders (apps/api, apps/jira-plus-plus, platform/, infra/, docker-compose.yml, Dockerfile.*).
- Identify GraphQL schema/resolvers, Prisma schema/models, Temporal workflows/activities, and UI routes/pages.

3) Generate diagrams from IR (final images)
Create diagrams in Mermaid (source) and export to PNG + SVG.

Outputs:
- Mermaid sources:
  - .artifacts/ai-generated/<TS>/diagrams/src/*.mmd
- Rendered:
  - .artifacts/ai-generated/<TS>/diagrams/png/*.png
  - .artifacts/ai-generated/<TS>/diagrams/svg/*.svg

Required diagrams (minimum):
A) Architecture / Component diagram
B) Data flow: Jira -> ingestion -> DB -> GraphQL -> Web UI
C) Sequence: Typical GraphQL request (UI -> API -> Prisma -> Postgres)
D) Sequence: Background workflow (API -> Temporal -> Worker -> DB)
E) Repo/Monorepo map (folders -> responsibilities)

Rendering:
- Use mermaid-cli (mmdc). If not installed, add it as a dev dependency in a temporary tooling folder or use npx.
- Ensure diagrams render deterministically (set theme variables only if needed).
- Validate Mermaid files compile; if any fail, fix and re-render.

4) Reconcile against expected outputs
Check if the repo contains any expected artifacts/diagrams (search for .artifacts/, docs/diagrams, specs diagrams).
- If expected diagram images exist, compare:
  - filenames and counts
  - Mermaid source equivalence (if available)
  - For images: do a lightweight comparison:
    - compare dimensions
    - compute perceptual hash OR compare SVG text structure
- If there is a “golden” set of artifacts under .artifacts/* (or similar), diff against it.
- Produce:
  - .artifacts/ai-generated/<TS>/reconcile/reconcile_report.md
  - .artifacts/ai-generated/<TS>/reconcile/diff_summary.json
Include:
- What was expected (paths found)
- What was generated
- Matches/mismatches and likely reasons
- Actionable fixes (e.g., “diagram naming differs”, “component missing: temporal worker”, etc.)

5) Final deliverable: single command
Create a script:
- scripts/ai_selftest_and_diagrams.sh (or .ps1 if Windows, but prefer bash)
It should run everything end-to-end:
- bootstrap (best-effort, idempotent)
- verify/tests
- IR generation
- diagram generation
- reconciliation
Return the command to run it.

6) Summarize results
Print a final summary to stdout AND save it to:
- .artifacts/ai-generated/<TS>/SUMMARY.md
Include:
- Setup steps taken
- Verification results (pass/fail)
- IR generated paths
- Diagrams generated (list)
- Reconciliation result (pass/fail) + key diffs
- Any blockers and how to fix

Now begin. Execute steps locally, write files, and keep logs. Do not stop on first failure; continue with partial outputs.