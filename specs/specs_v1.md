# Build a Code-to-PlantUML Visualization Application

## Overview
I want you to generate a complete application that takes source code as input, uses an LLM (OpenAI API) to parse and summarize the code structure, generates a PlantUML text specification representing the diagram, and then renders that specification to an image.

Use modular architecture and write in a maintainable way.

## Requirements

1. Use Node.js or Python (choose one, and justify choice in comments).
2. Create a CLI and REST API interface for:
   - Uploading code or pasting code text.
   - Choosing the diagram type (e.g., class diagram, sequence diagram).
3. The app should call OpenAI’s code-capable model (e.g., Codex or GPT code model) to:
   - Parse the input code and extract classes/modules/relationships.
   - Return a structured summary (JSON), and then convert that structure to a PlantUML text spec.
4. Generate PlantUML text like:
```
@startuml

@enduml
```
according to the relationships found in the code.
5. After generating PlantUML text, the app should:
- Render it using PlantUML CLI or PlantUML server (Graphviz, etc.).
- Save the rendered diagram image locally.
- Return the PlantUML text and the rendered image path in the API response.

## Features

✔ Input: source code file or pasted text  
✔ Uses OpenAI to *reason about code and output UML text*  
✔ Outputs: PlantUML text and rendered diagram image  
✔ CLI tool + REST API server  
✔ Config file for OpenAI key, diagram type preferences, and output paths

## Code Structure

- `/src`
- `index.js` or `app.py` → Entry point
- `server.js` or `server.py` → REST API
- `cli.js` or `cli.py` → CLI interface
- `openaiClient.js` or `openai_client.py` → Handles OpenAI calls
- `plantumlGenerator.js` or `plantuml_generator.py` → Converts structured code → PlantUML spec
- `renderer.js` or `renderer.py` → Handles rendering PlantUML using PlantUML CLI / server
- `/utils` → Helpers for parsing, formatting, etc.
- `/templates` → Example PlantUML templates

## Expected Behaviors

- Parsing code: ask LLM to list classes, interfaces, functions, modules
- Summarizing: LLM should output a JSON like:
```
{
“classes”: [
{ “name”: “User”, “methods”: [“login()”, “logout()”], “relations”: [“Order”] }
],
…
}
```
- Then convert that JSON into a PlantUML class diagram.

## Example Hard Requirements in Prompt

- Use `@startuml` and `@enduml` as PlantUML markers.  
- Ensure OpenAI model uses examples of PlantUML syntax.  
- Handle multiple languages (initially support at least Python and JavaScript).

## Documentation

- Add comments explaining each function and module purpose.
- Write example usage in README showing how to:
- Run CLI with code file
- Start API and POST code to generate UML
- Render and view image output

## Testing

- Add basic unit tests for:
- LLM calls (mock responses)
- PlantUML text generation
- Rendering output file

## Deliver Code

- Complete folder structure
- `package.json` or `requirements.txt` with dependencies
- Example code in `examples/`