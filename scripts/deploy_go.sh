#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GO_LOG_FILE="/tmp/archviz_go.log"
UI_LOG_FILE="/tmp/archviz_ui.log"
RENDERER_COMPOSE_FILE="$ROOT_DIR/docker-compose.renderers.yml"
UI_MODE="dev"

# By default start the Go backend

start_renderer_services() {
	if [[ ! -f "$RENDERER_COMPOSE_FILE" ]]; then
		return 0
	fi
	if ! command -v docker >/dev/null 2>&1; then
		echo "Docker not available; skipping renderer containers." >&2
		return 0
	fi
	local compose_cmd
	if docker compose version >/dev/null 2>&1; then
		compose_cmd=(docker compose)
	elif command -v docker-compose >/dev/null 2>&1; then
		compose_cmd=(docker-compose)
	else
		echo "Docker Compose not available; skipping renderer containers." >&2
		return 0
	fi

	echo "Bringing up renderer services (mermaid, structurizr)..."
	"${compose_cmd[@]}" -f "$RENDERER_COMPOSE_FILE" up -d --build
}

start_ui() {
	if [[ -f "$ROOT_DIR/ui/package.json" ]]; then
		if [[ -f "$ROOT_DIR/ui/package-lock.json" ]]; then
			INSTALL_CMD="npm ci"
		else
			INSTALL_CMD="npm install"
		fi
		(cd "$ROOT_DIR/ui" && $INSTALL_CMD --no-fund --no-audit )
			if [[ "$UI_MODE" == "dev" ]]; then
				# ensure no stale vite processes occupy the default port
				# kill any process listening on 5173, then any vite processes
				ss -ltnp | grep ':5173' || true | awk '{print $6}' | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | xargs -r kill -9 || true
				pkill -9 -f 'node .*vite' || pkill -9 -f 'vite' || true
				# start vite on fixed port 5173 so clients use a stable URL
				nohup bash -lc "cd '$ROOT_DIR/ui' && npm run dev -- --host 0.0.0.0 --port 5173" >"$UI_LOG_FILE" 2>&1 &
				echo "Started UI dev server (port 5173); log: $UI_LOG_FILE"
		else
			(cd "$ROOT_DIR/ui" && npm run build)
		fi
	fi
}

start_go_backend() {
	# Prefer building a binary for stability in deployments
	pushd "$ROOT_DIR/backend-go" >/dev/null
	if command -v go >/dev/null 2>&1; then
		if go build -o archviz_go ./cmd/server; then
			nohup ./archviz_go >"$GO_LOG_FILE" 2>&1 &
			echo "Go backend started (binary) — log: $GO_LOG_FILE"
		else
			echo "Go build failed; attempting go run fallback" >&2
			nohup go run ./cmd/server >"$GO_LOG_FILE" 2>&1 &
			echo "Go backend started (go run) — log: $GO_LOG_FILE"
		fi
	else
		echo "Go toolchain not found; cannot start Go backend" >&2
	fi
	popd >/dev/null
}

# kickoff
start_renderer_services
start_ui
start_go_backend

echo "Deployment initiated. Tail logs: tail -n 200 $GO_LOG_FILE"
if [[ "$UI_MODE" == "dev" ]]; then
	echo "UI dev server log: tail -n 200 $UI_LOG_FILE"
fi
