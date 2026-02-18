# Codex Prompt — Make GitHub Repo Ingestion Background Job with Loading UI

You are a senior full-stack engineer tasked with modifying the backend ingestion logic
so that **GitHub repository ingestion and IR generation runs as a background job**.

The goal is to:
1. Accept a repository URL from the UI
2. Immediately return a **job ID and status: queued**
3. Perform the heavy ingestion work asynchronously
4. Store the result (IR, summary, diagrams, metadata) when done
5. Let the UI poll the job status or use WebSockets until diagrams are ready
6. Render a loading indicator in the UI while the job runs  
7. Serve the final diagrams only when ingestion + IR generation completes

You must modify both the backend and UI accordingly.

---

## PART A — Backend Changes

### 1) Create a Job Queue Infrastructure
Introduce a background job system:
- In Python: use Celery or RQ
- In Go: use a worker pool / goroutine + queue
- In Node: use Bull or bee-queue

It must support:

enqueue_job(job_type=“ingest”, payload={“repo_url”: …})
return job_id
---

### 2) Modify Ingestion API

Replace the synchronous `ingest_github_repo(repo_url)` call in the HTTP handler with:
POST /api/ingest
Input: {“repo_url”: “…”}
Output: {“job_id”: “…”, “status”: “queued”}
The handler should:
- Validate URL
- Create a job entry in DB with status = “queued”
- Enqueue ingestion payload
- Return job_id immediately

---

### 3) Background Worker Logic

The worker must:
1. Update job status = “processing”
2. Clone the repo
3. Run existing structural extraction logic
4. Compute IR + diagrams
5. Store result in persistent storage (DB/S3)
6. Update job status = “complete”
7. Attach result locations (IR + diagrams)

If any error occurs:
- Update job status = “failed”
- Store error message

---

### 4) Job Status API

Add:
GET /api/ingest/{job_id}
Returns:
{
“job_id”: “…”,
“status”: “queued|processing|complete|failed”,
“result”: {
“ir”: {…},
“diagrams”: {…},
“warnings”: […]
},
“error”: null | “error message”
}

Ensure status updates are persisted.

---

### 5) Caching by Commit

When a job is enqueued:
- Compute commit hash from repo
- If a job for this repo+commit already exists in “complete”, return that result immediately
- Do NOT re-run ingestion

---

## PART B — UI Changes

### 1) Ingestion Trigger

When the user submits a GitHub URL:
- Call `POST /api/ingest`
- Show loading indicator / spinner
- Store `job_id`

### 2) Poll Status

Every N seconds (e.g., 2–3s):
- Call `GET /api/ingest/{job_id}`
- While status = “queued” or “processing”, keep loading indicator
- When status = “complete”, fetch diagrams and render
- If status = “failed”, show error message

### 3) UX Loading Design

UI must show:
- “Analyzing repository…”
- Progress indicator
- Optional ETA based on status
- On complete → fade to diagrams

---

## PART C — Backend Data Model

### Job Record Structure
Create a persistent storage for jobs:
Job {
id: UUID,
repo_url: string,
commit_hash: string | null,
status: “queued|processing|complete|failed”,
result: JSON | null,
error: text | null,
created_at: timestamp,
updated_at: timestamp
}

---

## PART D — Testing Requirements

### Test 1 — Enqueue Job
- Submit `/api/ingest`
- Expect response with job_id and status “queued”
- No timeout

### Test 2 — Job Status Transition
- After submission, GET `/api/ingest/{job_id}`
- Expect transitions: queued → processing → complete

### Test 3 — Worker Success
- Worker runs ingestion in background
- Job eventually completes
- result contains IR + diagram metadata

### Test 4 — UI Loading Indicator
- UI must remain responsive
- Loading indicator persists until status = complete
- On completion, diagrams render

### Test 5 — Failure Handling
- Submit invalid GitHub URL
- Job status becomes “failed”
- UI shows clear error

### Test 6 — Caching by Commit
- Ingest same repo twice
- Second call returns existing result immediately

Ensure all tests pass automatically via existing test harness and Cypress.

---

## PART E — Requirements

- Do not make user wait for ingestion synchronously
- UI must show a loading screen until ingestion is complete
- Results must be persisted and retrievable by job_id
- Diagrams must only be shown after ingestion is complete
- No request timeout errors due to heavy syncing
- Ensure idempotent operations via commit hashing