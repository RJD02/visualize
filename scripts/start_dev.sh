#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "Missing .env at $ENV_FILE" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Start required services manually." >&2
  exit 1
fi

start_postgres() {
  local name="${ARCHVIZ_PG_CONTAINER:-archviz-postgres}"

  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL not set; skipping Postgres container startup." >&2
    return 0
  fi

  local parsed
  parsed="$($ROOT_DIR/.venv/bin/python - <<'PY'
import os
from urllib.parse import urlparse

db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    raise SystemExit(1)
parsed = urlparse(db_url)
user = parsed.username or ""
password = parsed.password or ""
host = parsed.hostname or ""
port = parsed.port or 5432
name = parsed.path.lstrip("/")
print(user)
print(password)
print(host)
print(port)
print(name)
PY
  )"

  local user password host port db
  user="$(echo "$parsed" | sed -n '1p')"
  password="$(echo "$parsed" | sed -n '2p')"
  host="$(echo "$parsed" | sed -n '3p')"
  port="$(echo "$parsed" | sed -n '4p')"
  db="$(echo "$parsed" | sed -n '5p')"

  if [[ "$host" != "localhost" && "$host" != "127.0.0.1" ]]; then
    echo "DATABASE_URL points to $host; skipping local Postgres container." >&2
    return 0
  fi

  local running_postgres
  running_postgres="$(docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}' | grep -E 'postgres|pgvector' || true)"
  if [[ -n "$running_postgres" ]] && ! echo "$running_postgres" | cut -f1 | grep -q "^${name}$"; then
    echo "Detected a running Postgres container:\n$running_postgres" >&2
    echo "Using the existing Postgres container. If credentials don't match, update DATABASE_URL." >&2
    return 0
  fi

  if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
    echo "Postgres container '${name}' already running."
  elif docker ps -a --format '{{.Names}}' | grep -q "^${name}$"; then
    echo "Starting existing Postgres container '${name}'..."
    docker start "$name" >/dev/null
  else
    echo "Creating Postgres container '${name}'..."
    docker run -d \
      --name "$name" \
      -e POSTGRES_USER="$user" \
      -e POSTGRES_PASSWORD="$password" \
      -e POSTGRES_DB="$db" \
      -p "${port}:5432" \
      postgres:15-alpine >/dev/null
  fi

  echo "Waiting for Postgres to be ready..."
  for _ in {1..30}; do
    if docker exec "$name" pg_isready -U "$user" -d "$db" >/dev/null 2>&1; then
      echo "Postgres is ready."
      return 0
    fi
    sleep 1
  done

  echo "Postgres did not become ready in time." >&2
  exit 1
}

start_plantuml() {
  local name="${ARCHVIZ_PLANTUML_CONTAINER:-plantuml-server}"

  if [[ -z "${PLANTUML_SERVER_URL:-}" ]]; then
    echo "PLANTUML_SERVER_URL not set; skipping PlantUML container startup." >&2
    return 0
  fi

  if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
    echo "PlantUML container '${name}' already running."
  elif docker ps -a --format '{{.Names}}' | grep -q "^${name}$"; then
    echo "Starting existing PlantUML container '${name}'..."
    docker start "$name" >/dev/null
  else
    echo "Creating PlantUML container '${name}'..."
    docker run -d \
      --name "$name" \
      -p 8080:8080 \
      plantuml/plantuml-server >/dev/null
  fi
}

start_api() {
  local python_bin="$ROOT_DIR/.venv/bin/python"
  if [[ ! -x "$python_bin" ]]; then
    python_bin="python3"
  fi

  echo "Starting API server..."
  exec "$python_bin" -m src.app
}

start_postgres
start_plantuml
start_api
