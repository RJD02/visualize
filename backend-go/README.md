# backend-go

Go backend entrypoint:

- `go run ./cmd/server`

Current implementation runs a Go HTTP server on `PORT` (default `8000`) and proxies requests to an embedded Python backend running on `PY_BACKEND_INTERNAL_PORT` (default `18000`).

Environment variables:

- `PORT` (default: `8000`)
- `GO_BACKEND_UPSTREAM` (default: `http://127.0.0.1:${PY_BACKEND_INTERNAL_PORT}`)
- `GO_START_EMBEDDED_PYTHON` (`1` by default)
- `PY_BACKEND_INTERNAL_PORT` (default: `18000`)
- `PYTHON_BIN` (default: `.venv/bin/python` if present)

This preserves frontend and MCP API compatibility while the native Go implementation is incrementally expanded.
