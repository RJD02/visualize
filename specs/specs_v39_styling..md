We are introducing a new rule:

All edit operations must be routed through the Styling Agent.

An edit is defined as:
(previous IR) + (user edit suggestion)

The Styling Agent must handle both styling and controlled structural edits.

The system must not crash, recurse infinitely, or overwrite IR fields accidentally.

Implement the following architecture changes carefully.

First, update the Main Agent logic.

The Main Agent must no longer mutate IR directly when the user submits an edit. Instead:
	1.	Detect edit intent from user message.
	2.	Always pass:
	•	the current canonical IR
	•	the user edit suggestion
	•	optional diagram metadata
	3.	Route this payload to the Styling Agent.
	4.	Wait for the Styling Agent’s structured response.
	5.	Validate the response.
	6.	Apply deterministic patching.
	7.	Store a new IR version.
	8.	Re-render diagram.
	9.	Log audit trail.

The Main Agent must never directly overwrite IR with LLM output.

Second, refactor the Styling Agent into a pure transformation agent.

The Styling Agent must:
	•	Accept:
	•	ir (required)
	•	user_edit_suggestion (optional string)
	•	mode (optional, default “style_only”)
	•	constraints (optional rules)
	•	Call the LLM to interpret the intent.
	•	Produce one of the following outputs:
	1.	patch_ops (preferred)
	2.	updated_ir (fallback only)
	3.	structured error message

The Styling Agent must NOT:
	•	Call the Main Agent
	•	Call rendering endpoints
	•	Trigger ingestion
	•	Modify database
	•	Perform side effects

It must be pure and return structured transformation data only.

Third, enforce a strict response contract.

The Styling Agent must return:

Either:
{
“patch_ops”: […]
}

Or:
{
“updated_ir”: {…}
}

Or:
{
“error”: “…”,
“explanation”: “…”
}

If the response does not match this schema, the Main Agent must reject it safely and return a controlled error to the UI. The server must not crash.

Fourth, implement deterministic patch application.

If patch_ops is returned:
	•	Validate each patch path is allowed.
	•	Only allow modifications to:
	•	node styles
	•	edge styles
	•	labels
	•	zones
	•	globalIntent aesthetic fields
	•	explicitly allowed structural edits
	•	Disallow:
	•	arbitrary key injection
	•	removal of required IR sections
	•	invalid node references
	•	orphan edge creation

Apply patches on a deep copy of the IR.

After patching:
	•	Run structural validation.
	•	Ensure required fields still exist.
	•	Ensure no orphan edges.
	•	Ensure node IDs remain unique.
	•	Ensure no recursion introduced.

If validation fails:
	•	Abort edit
	•	Log audit failure
	•	Return error safely

If updated_ir is returned:
	•	Validate schema completeness.
	•	Ensure all required IR fields exist.
	•	Merge with previous IR if partial.
	•	Reject if core sections missing.

Fifth, implement IR versioning and audit trail.

For every edit:
	•	Create new IR version:
	•	ir_version incremented
	•	parent_version recorded
	•	Store:
	•	user_edit_suggestion
	•	patch_ops or diff summary
	•	validation result
	•	timestamp

Expose this via:
get_ir_history endpoint.

Sixth, prevent recursion and tool loops.

Ensure:
	•	Styling Agent cannot call Main Agent.
	•	Styling Agent cannot call MCP tools except LLM.
	•	No infinite edit → restyle → edit cycles.

Add timeouts to LLM calls.
If LLM times out:
	•	Return controlled fallback response.

Seventh, update tests.

Add the following tests:
	1.	Edit smoke test:
	•	Submit edit suggestion.
	•	Assert new IR version created.
	•	Assert diagram renders successfully.
	2.	Patch validation test:
	•	Styling Agent returns invalid patch path.
	•	Main Agent rejects safely.
	•	Server does not crash.
	3.	Structural integrity test:
	•	Edit removes node referenced by edge.
	•	Validation fails.
	•	Error returned gracefully.
	4.	No recursion test:
	•	Styling Agent never invokes Main Agent.
	•	No infinite loop.
	5.	Version history test:
	•	Multiple edits produce version chain.
	•	History retrievable.

All tests must pass.

Eighth, enforce philosophy:
	•	LLM assists.
	•	IR is canonical.
	•	Main Agent controls determinism.
	•	Styling Agent interprets intent.
	•	Validation enforces integrity.
	•	Rendering happens only after validation.

The goal is to eliminate:
	•	server crashes
	•	invalid IR overwrites
	•	infinite loops
	•	uncontrolled LLM modifications

The system must become:

A deterministic architecture modeling runtime with AI-assisted transformation.

Implement these changes without breaking existing API contracts, rendering logic, or frontend behavior.

If something is ambiguous, choose safety and determinism over flexibility.