# Code-to-PlantUML Visualization

A Python CLI + REST API + UI to parse code/docs, generate an ArchitecturePlan, render PlantUML, and optionally create SDXL visuals. Orchestration runs strictly through Google ADK runtime APIs.

## Setup

1. Create a virtual env and install dependencies.
2. Copy `.env.example` to `.env` and set `OPENAI_API_KEY` and `HF_API_TOKEN`.

## CLI Usage

Generate from file(s) (code or .docx):

```
python -m src.cli --file examples/sample.py --file examples/sample.js --output-name sample_multi
python -m src.cli --file examples/architecture.docx --output-name architecture
```

Generate from pasted text:

```
python -m src.cli --text "class A: pass" --output-name quick
```

## API Usage

Start server (includes UI at /):

```
python -m src.app
```

POST code:

```
curl -X POST http://localhost:8000/generate \
  -F "files=@examples/sample.py" \
  -F "files=@examples/architecture.docx" \
  -F "output_name=docx_mix"
```

Response includes architecture plan, PlantUML diagram files, and SDXL prompt + image file (requires HF model access). ADK is used for orchestration.

## UI

Open the UI at http://localhost:8000/ or http://localhost:8000/ui after starting the server. It supports uploads, generation, and iterative image edits.

## ADK Flow

The workflow is executed through Google ADK runtime APIs:

1. Text extraction
2. `ArchitectAgent` produces ArchitecturePlan JSON
3. `DiagramAgent` generates PlantUML diagrams
4. `VisualAgent` renders SDXL image
5. `EvaluatorAgent` produces quality score

Image edits call `ImageEditAgent` only and reuse the stored ArchitecturePlan.

## Tests

```
pytest
```

UI Cypress (from ui/):

```
cd ui
npm install
npx cypress run --spec cypress/e2e/diagram-feedback.cy.ts
```
