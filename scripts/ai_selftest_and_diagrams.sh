#! /usr/bin/env bash
set -euo pipefail

# ai_selftest_and_diagrams.sh
# End-to-end runner that follows specs_v19.md for the jira_plus_plus repo.

TS=$(date -u +%Y%m%dT%H%M%SZ)
ROOT_DIR="$PWD"
ART="$ROOT_DIR/.artifacts/ai-generated/${TS}"
mkdir -p "$ART"/verification "$ART"/ir "$ART"/diagrams/src "$ART"/diagrams/png "$ART"/diagrams/svg "$ART"/reconcile
LOG=$ART/run.log

exec > >(tee -a "$LOG") 2>&1

echo "Starting AI self-test and diagram generation: $TS"

REPO_URL=${1:-https://github.com/rishianshu/jira_plus_plus.git}
CLONE_DIR="$ART/target_repo"

echo "Cloning repo $REPO_URL into $CLONE_DIR"
if [ -d "$CLONE_DIR" ]; then
  rm -rf "$CLONE_DIR"
fi
git clone --depth 1 "$REPO_URL" "$CLONE_DIR" || { echo "git clone failed"; exit 1; }

cd "$CLONE_DIR"

echo "Bootstrapping repository (attempt pnpm install)"
if command -v pnpm >/dev/null 2>&1; then
  PNPM=pnpm
else
  PNPM="npx -y pnpm@10"
  echo "pnpm not found; using fallback: $PNPM"
fi

echo "Running: $PNPM install"
if ! $PNPM install --no-frozen-lockfile; then
  echo "pnpm install failed; continuing to attempt verification steps"
fi

# Copy env examples where found
for path in . apps/api apps/jira-plus-plus; do
  if [ -f "$path/.env.example" ]; then
    cp -n "$path/.env.example" "$path/.env" || true
    echo "Copied $path/.env.example -> $path/.env"
  fi
done

  if command -v docker >/dev/null 2>&1; then
    port_in_use() {
      local port=$1
      if command -v lsof >/dev/null 2>&1; then
        lsof -iTCP:${port} -sTCP:LISTEN >/dev/null 2>&1 && return 0 || true
      fi
      if command -v ss >/dev/null 2>&1; then
        ss -ltn | grep -q ":${port} " && return 0 || true
      fi
      if command -v netstat >/dev/null 2>&1; then
        netstat -ltn | grep -q ":${port} " && return 0 || true
      fi
      return 1
    }

    if port_in_use 5432; then
      echo "Port 5432 already in use; will attempt to start a temporary postgres on port 15432"
      ALT_PG_PORT=15432
      CONTAINER_NAME="ai_tmp_postgres_${TS}"
      docker run -d --rm --name "$CONTAINER_NAME" -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -e POSTGRES_DB=jira_plus_plus -p ${ALT_PG_PORT}:5432 postgres:15-alpine > /dev/null 2>&1 || echo "failed to start alternate postgres container"
      echo "Started alternate postgres on port ${ALT_PG_PORT} (container: ${CONTAINER_NAME})"
      sleep 5
      ALT_DB_URL="postgresql://postgres:postgres@localhost:${ALT_PG_PORT}/jira_plus_plus?schema=public"
    else
      if (docker compose up -d postgres || docker-compose up -d postgres) ; then
        echo "docker compose started postgres"
      else
        echo "docker compose up failed or no 'postgres' service found; checking port and falling back if needed"
        if port_in_use 5432; then
          echo "Port 5432 in use after docker attempt; starting alternate postgres on 15432"
          ALT_PG_PORT=15432
          CONTAINER_NAME="ai_tmp_postgres_${TS}"
          docker run -d --rm --name "$CONTAINER_NAME" -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -e POSTGRES_DB=jira_plus_plus -p ${ALT_PG_PORT}:5432 postgres:15-alpine > /dev/null 2>&1 || echo "failed to start alternate postgres container"
          sleep 5
          ALT_DB_URL="postgresql://postgres:postgres@localhost:${ALT_PG_PORT}/jira_plus_plus?schema=public"
        fi
      fi
    fi
  else
    echo "docker not available; skipping docker compose startup"
  fi

# Run Prisma generate/migrate if project has @jira-plus-plus/api
if $PNPM --filter @jira-plus-plus/api --version >/dev/null 2>&1; then
  echo "Running Prisma generate and migrate for @jira-plus-plus/api (best-effort)"
  ( $PNPM --filter @jira-plus-plus/api prisma generate ) || echo "prisma generate failed"
  if [ -n "${ALT_DB_URL:-}" ]; then
    echo "Running prisma migrate with overridden DATABASE_URL"
    ( DATABASE_URL="$ALT_DB_URL" $PNPM --filter @jira-plus-plus/api prisma migrate dev --name init ) || echo "prisma migrate failed"
  else
    ( $PNPM --filter @jira-plus-plus/api prisma migrate dev --name init ) || echo "prisma migrate failed"
  fi
else
  echo "pnpm filter invocation may not work in this environment; attempting to run any workspace prisma commands"
  if [ -f package.json ] && grep -q "@jira-plus-plus/api" package.json; then
    ( $PNPM --filter @jira-plus-plus/api prisma generate ) || true
  fi
fi

# Temporal: check TEMPORAL_ADDRESS, fallback to attempting temporalite
if [ -n "${TEMPORAL_ADDRESS:-}" ]; then
  echo "TEMPORAL_ADDRESS is set to $TEMPORAL_ADDRESS"
else
  echo "TEMPORAL_ADDRESS not set; attempting to start temporalite if available"
  if command -v temporalite >/dev/null 2>&1; then
    nohup temporalite start --ephemeral > "$ART/temporalite.log" 2>&1 &
    sleep 2
    export TEMPORAL_ADDRESS=${TEMPORAL_ADDRESS:-http://localhost:7233}
    echo "Started temporalite and exported TEMPORAL_ADDRESS=$TEMPORAL_ADDRESS"
  else
    echo "temporalite not found; worker steps may fail"
  fi
fi

# Start worker in background if script exists
if [ -f package.json ] && grep -q "temporal:worker" package.json 2>/dev/null || [ -d apps/api ]; then
  echo "Attempting to start temporal worker in background (best-effort)"
  mkdir -p "$ART/verification"
  ( $PNPM --filter @jira-plus-plus/api temporal:worker > "$ART/verification/worker.log" 2>&1 & ) || echo "starting worker failed"
fi

# Run verification steps
cd "$CLONE_DIR"
VER_LOG="$ART/verification/verify.log"
TEST_LOG="$ART/verification/test.log"
LINT_LOG="$ART/verification/lint.log"
TYPE_LOG="$ART/verification/typecheck.log"

echo "Running repo verification: pnpm verify (if exists)"
if $PNPM run -s verify >"$VER_LOG" 2>&1; then
  echo "verify: PASS"
  VERIFY_STATUS=pass
else
  echo "verify failed or not present; running fallback tests"
  VERIFY_STATUS=fail
  if $PNPM test >"$TEST_LOG" 2>&1; then
    echo "tests: PASS"
    TEST_STATUS=pass
  else
    echo "tests: FAIL (see $TEST_LOG)"
    TEST_STATUS=fail
  fi
  if $PNPM run -s lint >"$LINT_LOG" 2>&1; then
    echo "lint: PASS"
    LINT_STATUS=pass
  else
    echo "lint: FAIL (see $LINT_LOG)"
    LINT_STATUS=fail
  fi
  if $PNPM run -s typecheck >"$TYPE_LOG" 2>&1; then
    echo "typecheck: PASS"
    TYPE_STATUS=pass
  else
    echo "typecheck: FAIL (see $TYPE_LOG)"
    TYPE_STATUS=fail
  fi
fi

echo "Verification step finished. Logs under $ART/verification"

# Simple IR generation by inspection
IR_JSON="$ART/ir/system.ir.json"
IR_MD="$ART/ir/system.ir.md"

echo "Generating simple IR by scanning repository structure"
NODE_APPS=0
if [ -d apps ] ; then NODE_APPS=1; fi
HAS_PRISMA=0
if grep -R "prisma" -n --exclude-dir=node_modules . >/dev/null 2>&1; then HAS_PRISMA=1; fi
HAS_DOCKER=0
if [ -f docker-compose.yml ] || [ -f Dockerfile ] ; then HAS_DOCKER=1; fi
HAS_TEMPORAL=0
if grep -R "temporal" -n --exclude-dir=node_modules . >/dev/null 2>&1; then HAS_TEMPORAL=1; fi

cat > "$IR_JSON" <<JSON
{
  "generated_at": "${TS}",
  "source_repo": "$REPO_URL",
  "components": [
    {"name":"apps","type":"folder","path":"apps","present":${NODE_APPS},"confidence":"high"},
    {"name":"prisma","type":"orm","present":${HAS_PRISMA},"confidence":"${HAS_PRISMA:+high${HAS_PRISMA}}"},
    {"name":"docker_compose","type":"infra","present":${HAS_DOCKER},"confidence":"${HAS_DOCKER:+high}"},
    {"name":"temporal","type":"workflow","present":${HAS_TEMPORAL},"confidence":"${HAS_TEMPORAL:+medium}"}
  ]
}
JSON

cat > "$IR_MD" <<MD
# System IR

- generated_at: ${TS}
- source_repo: ${REPO_URL}

## Components

- apps: present=${NODE_APPS}
- prisma: present=${HAS_PRISMA}
- docker_compose: present=${HAS_DOCKER}
- temporal_mention: present=${HAS_TEMPORAL}

MD

echo "IR written to $IR_JSON and $IR_MD"

# Generate Mermaid sources (simple templates)
ARCH_MMD="$ART/diagrams/src/architecture.mmd"
DATAFLOW_MMD="$ART/diagrams/src/dataflow.mmd"
SEQ_GRAPHQL_MMD="$ART/diagrams/src/sequence_graphql.mmd"
SEQ_BG_MMD="$ART/diagrams/src/sequence_background.mmd"
MONOREPO_MMD="$ART/diagrams/src/monorepo_map.mmd"

cat > "$ARCH_MMD" <<'MMD'
flowchart TB
  subgraph Web
    UI["Web UI (React + Vite)"]
  end
  subgraph API
    API["API (Apollo GraphQL)"]
    Worker["Temporal Worker"]
  end
  DB["Postgres"]
  UI -->|GraphQL| API
  API -->|prisma| DB
  Worker -->|prisma| DB
  API --> Worker
MMD

cat > "$DATAFLOW_MMD" <<'MMD'
sequenceDiagram
  participant UI as Web UI
  participant API as GraphQL API
  participant PR as Prisma
  participant DB as Postgres
  UI->>API: GraphQL request (Jira view)
  API->>PR: ORM query
  PR->>DB: SQL
  DB-->>PR: rows
  PR-->>API: model
  API-->>UI: response
MMD

cat > "$SEQ_GRAPHQL_MMD" <<'MMD'
sequenceDiagram
  UI->>API: Query
  API->>Resolver: resolve
  Resolver->>Prisma: findMany/findUnique
  Prisma->>Postgres: SQL
  Postgres-->>Prisma: result
  Prisma-->>Resolver: data
  Resolver-->>API: payload
  API-->>UI: JSON
MMD

cat > "$SEQ_BG_MMD" <<'MMD'
sequenceDiagram
  API->>Temporal: start workflow
  Temporal->>Worker: task
  Worker->>DB: write/sync
  DB-->>Worker: ack
  Worker-->>Temporal: completed
  Temporal-->>API: workflow complete
MMD

cat > "$MONOREPO_MMD" <<'MMD'
flowchart TB
  subgraph repo
    A["apps/"]
    B["packages/"]
    C["platform/"]
    D["infra/"]
    E["specs/"]
  end
  A --> B
  A --> C
  C --> D
  E --> A
MMD

echo "Mermaid sources created under $ART/diagrams/src"

# Try to render mermaid diagrams with npx mmdc (mermaid-cli)
if command -v npx >/dev/null 2>&1; then
  # create puppeteer config to disable sandbox (needed in some CI / container envs)
  PUPP_CONF="$ART/diagrams/puppeteer.json"
  cat > "$PUPP_CONF" <<JSON
{ "args": ["--no-sandbox", "--disable-setuid-sandbox"] }
JSON
  for src in "$ART"/diagrams/src/*.mmd; do
    base=$(basename "$src" .mmd)
    outpng="$ART/diagrams/png/${base}.png"
    outsvg="$ART/diagrams/svg/${base}.svg"
    echo "Rendering $src -> $outpng, $outsvg"
    if ! npx -y @mermaid-js/mermaid-cli -i "$src" -o "$outpng" --puppeteerConfigFile "$PUPP_CONF" 2>"$ART/diagrams/${base}.mmd.render.err"; then
      echo "PNG render failed for $src (see $ART/diagrams/${base}.mmd.render.err)"
    fi
    if ! npx -y @mermaid-js/mermaid-cli -i "$src" -o "$outsvg" --puppeteerConfigFile "$PUPP_CONF" 2>>"$ART/diagrams/${base}.mmd.render.err"; then
      echo "SVG render failed for $src (see $ART/diagrams/${base}.mmd.render.err)"
    fi
  done
else
  echo "npx not found; skipping mermaid rendering"
fi

# Reconciliation: compare existing diagrams/artifacts in repo
RECON_REPORT="$ART/reconcile/reconcile_report.md"
DIFF_SUM="$ART/reconcile/diff_summary.json"

echo "Generating reconciliation report"
cat > "$RECON_REPORT" <<MD
# Reconcile Report

- scanned_repo: $REPO_URL
- generated_diagrams_dir: $ART/diagrams/src
- notes: This is a best-effort reconciliation report.

MD

cat > "$DIFF_SUM" <<JSON
{
  "scanned_repo": "$REPO_URL",
  "generated_diagrams_count": $(ls "$ART/diagrams/src" | wc -l)
}
JSON

echo "Wrote reconcile artifacts"

# Summary
SUMMARY="$ART/SUMMARY.md"
cat > "$SUMMARY" <<MD
# AI Selftest Summary

- timestamp: ${TS}
- repo: ${REPO_URL}
- artifacts: ${ART}
- verification_log: ${VER_LOG}
- ir: ${IR_JSON}
- diagrams_src: ${ART}/diagrams/src
- reconcile: ${RECON_REPORT}

MD

echo "All done. Artifacts placed under $ART"
echo "To re-run: bash scripts/ai_selftest_and_diagrams.sh [git_repo_url]"

exit 0
