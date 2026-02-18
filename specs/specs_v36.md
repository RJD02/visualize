# Codex Prompt — Intelligent GitHub Ingestion for Architecture Diagrams

You are responsible for implementing a GitHub ingestion pipeline
for the diagram generation system.

The goal is to extract architectural structure from a repository
WITHOUT ingesting the entire codebase or function-level logic.

We are building an architecture modeling engine, not a static analyzer.

Do NOT parse every file.
Do NOT ingest function bodies.
Do NOT ingest tests or vendor dependencies.
Do NOT overfit to internal utility code.

We want structural signal, not code volume.

---

# OBJECTIVE

Given a GitHub repository URL, extract only the information necessary
to generate accurate system-level, container-level, and component-level diagrams.

The ingestion must:

- Be deterministic
- Avoid hallucinating structure
- Avoid fabricating services
- Avoid reading unnecessary code
- Produce structured IR-ready output

---

# INGESTION STRATEGY

Implement the following structured pipeline:

---

## 1. Repository Metadata Scan

Extract:

- README.md (if present)
- go.mod / package.json / requirements.txt
- Dockerfile
- docker-compose.yml
- CI/CD configs
- deployment files
- configuration files

Purpose:
- Identify language
- Identify framework
- Identify entry points
- Identify infrastructure
- Identify external services

Do NOT extract implementation details.

---

## 2. Directory Structure Mapping

Build a directory tree excluding:

- node_modules
- vendor
- dist
- build
- .git
- test folders (unless explicitly referenced in README)

Extract:

- Top-level directories
- Internal package/module structure
- Clear boundaries (handlers, services, repo, models, etc.)

Produce:

A structural map of folders → logical modules.

---

## 3. Entry Point Detection

Locate:

- main.go
- index.js / server.js
- app entry files
- router initialization files

From entry point:

- Trace router definitions
- Identify controllers/handlers
- Identify service layer references
- Identify repository/data layer references

Do NOT parse function bodies.
Only extract structural calls and imports.

---

## 4. Package Dependency Graph

Extract import relationships:

- package A imports package B
- module A depends on module B

Build a dependency graph at package level.

Avoid function-level call graphs.

This graph is used to infer:

- Layered architecture
- Dependency direction
- Coupling

---

## 5. External Integration Detection

From code imports and config files, detect:

- Database usage
- Redis
- Kafka
- S3
- SMTP
- Third-party APIs
- OAuth providers

Only mark integrations that are explicitly imported or configured.

Do NOT assume external services.

---

## 6. IR Construction Rules

When building IR:

- Only create nodes for explicitly detected modules.
- Only create edges for explicitly observed dependencies.
- If structure is inferred, mark:

  "inferred": true
  "confidence": < 0.8

- Do NOT fabricate “Compute Services” or abstract containers unless clearly implied.

IR must reflect structural architecture, not speculative architecture.

---

# STRICT RULES

1. Do NOT ingest entire repository contents into LLM context.
2. Do NOT extract function bodies.
3. Do NOT build call graphs unless explicitly requested.
4. Do NOT hallucinate missing components.
5. Do NOT assume microservices unless clearly separated.
6. Do NOT treat README suggestions as confirmed runtime structure.
7. Do NOT treat test dependencies as production architecture.

If information is ambiguous:
- Lower confidence
- Mark as inferred
- Do NOT assert as fact

---

# OUTPUT FORMAT

The ingestion pipeline must output:

- repository_summary
- directory_structure_map
- entry_points
- dependency_graph
- detected_integrations
- structured_architecture_ir

All in structured JSON, ready for rendering.

---

# VALIDATION

Before marking ingestion complete:

- Ensure no fabricated services exist.
- Ensure no orphan modules.
- Ensure dependency graph is acyclic unless explicitly cyclic.
- Ensure confidence values reflect certainty.

If ambiguity is high:
Return structured warning instead of guessing.

---

# PHILOSOPHY

Architecture extraction ≠ code ingestion.

Architecture is structural abstraction.

This system must prioritize:

Clarity > Volume  
Structure > Completeness  
Determinism > Creativity  
Honesty > Guessing  

Implement accordingly.