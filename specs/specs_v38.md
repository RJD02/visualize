You are a senior systems engineer tasked with migrating the entire backend of the diagram application from Python to Go. This is a parallel migration, not a destructive rewrite. Do NOT delete or modify existing Python logic beyond moving it into a dedicated folder. The goal is to create a production-grade Go backend that mirrors all existing functionality exactly, while preserving API contracts so the frontend continues working without any changes.

First, restructure the repository so that all existing Python backend code is moved into a folder named backend-python. Create a new folder named backend-go for the Go implementation. The frontend must remain untouched. Ensure that both backends can coexist and run independently.

The Go backend must replicate every existing API endpoint exactly. Routes, request bodies, response schemas, status codes, and error formats must remain identical. The UI must not experience any API failures, port mismatches, CORS issues, or schema drift. If the Python backend runs on a specific port, the Go backend must default to the same port configuration.

Re-implement the following subsystems in Go:
	1.	IR engine:
	•	Define strongly typed Go structs representing IR nodes, edges, globalIntent, nodeIntent, edgeIntent, aestheticIntent, metadata, and confidence.
	•	Implement deterministic IR mutation logic (block-level editability).
	•	Maintain versioning with parent_version tracking.
	•	Preserve audit logs for feedback mutations.
	•	Ensure no hallucinated nodes or edges are introduced.
	2.	GitHub ingestion system:
	•	Implement asynchronous background ingestion (no blocking HTTP requests).
	•	Use goroutines and a worker queue pattern.
	•	Support job creation via POST /api/ingest returning job_id.
	•	Implement GET /api/ingest/{job_id} to check job status.
	•	Cache ingestion results by repo URL + commit hash.
	•	Ensure ingestion cannot cause server timeouts.
	3.	Rendering orchestration:
	•	Implement Docker process execution using exec.Command.
	•	Capture stdout/stderr safely.
	•	Enforce timeouts for subprocess calls.
	•	Ensure Mermaid and PlantUML rendering behave exactly as before.
	•	Preserve deterministic output.
	4.	Styling and animation integration:
	•	Support post-SVG CSS injection.
	•	Maintain animation spec handling.
	•	Ensure no changes to frontend rendering expectations.
	5.	MCP tool exposure:
	•	Expose the Go backend as diagram_architect_agent.
	•	Support actions: generate_diagram, update_diagram, get_ir, get_ir_history, export_svg, export_gif.
	•	Ensure schema compatibility with existing integration.

Update the deploy script so it accepts an argument specifying which backend to run. Example:
./deploy.sh python
./deploy.sh go
Default behavior should remain Python until Go is verified stable.

All existing automated tests must pass against the Go backend. This includes:
	•	Unit tests
	•	Integration tests
	•	Cypress tests
	•	Feedback loop tests
	•	Styling validation tests

If any test fails:
	1.	Compare Python and Go behavior.
	2.	Fix Go implementation to match Python behavior.
	3.	Re-run tests.
	4.	Repeat until all tests pass.

Do not modify tests unless absolutely required. If a test change is necessary, document clearly why.

Strict constraints:
	•	Do not break the frontend.
	•	Do not alter API contracts.
	•	Do not simplify IR schema.
	•	Do not remove auditability.
	•	Do not remove deterministic mutation.
	•	Do not bypass failing tests.
	•	Do not introduce concurrency race conditions; ensure IR mutation is thread-safe.
	•	Use structured logging.
	•	Maintain graceful error handling.

Success criteria:
	•	Python backend still runs independently.
	•	Go backend runs independently.
	•	Deploy script can switch between them.
	•	All tests pass under both implementations.
	•	UI behavior is indistinguishable between Python and Go.
	•	Background ingestion does not cause timeouts.
	•	MCP integration works correctly.
	•	Deterministic IR mutation and version history are preserved.

The migration is complete only when the Go backend achieves full behavioral parity with Python and passes all automated validations without regression.