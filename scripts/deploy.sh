#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="/tmp/archviz_server.log"
UI_LOG_FILE="/tmp/archviz_ui.log"
UI_MODE="dev"
RENDERER_COMPOSE_FILE="$ROOT_DIR/docker-compose.renderers.yml"

pkill -f "src.app|uvicorn|start_dev.sh" || true
pkill -f "vite" || true

start_renderer_services() {
	if [[ ! -f "$RENDERER_COMPOSE_FILE" ]]; then
		return 0
	fi
	if ! command -v docker >/dev/null 2>&1; then
		echo "Docker is not installed; skipping renderer containers." >&2
		return 0
	fi
	local compose_cmd
	if docker compose version >/dev/null 2>&1; then
		compose_cmd=(docker compose)
	elif command -v docker-compose >/dev/null 2>&1; then
		compose_cmd=(docker-compose)
	else
		echo "Docker Compose is not available; skipping renderer containers." >&2
		return 0
	fi

	echo "Bringing up renderer services (mermaid, structurizr)..."
	"${compose_cmd[@]}" -f "$RENDERER_COMPOSE_FILE" up -d --build
}

start_renderer_services

if [[ -f "$ROOT_DIR/ui/package.json" ]]; then
	if [[ -f "$ROOT_DIR/ui/package-lock.json" ]]; then
		INSTALL_CMD="npm ci"
	else
		INSTALL_CMD="npm install"
	fi
	if [[ "$UI_MODE" == "dev" ]]; then
		(cd "$ROOT_DIR/ui" && $INSTALL_CMD --no-fund --no-audit && nohup npm run dev -- --host 0.0.0.0 >"$UI_LOG_FILE" 2>&1 &)
	else
		(cd "$ROOT_DIR/ui" && $INSTALL_CMD --no-fund --no-audit && npm run build)
	fi
fi

nohup "$ROOT_DIR/scripts/start_dev.sh" >"$LOG_FILE" 2>&1 &

echo "Deployment complete. Tail logs: tail -n 200 $LOG_FILE"
if [[ "$UI_MODE" == "dev" ]]; then
	echo "UI dev server log: tail -n 200 $UI_LOG_FILE"
fi
