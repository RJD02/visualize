# Build an Intelligent Code & Architecture Diagram Generator

## Objective
Create a complete application that accepts **source code files** (Python, JavaScript, Java, C#, etc.) and **.docx architecture documents**, and produces **PlantUML diagram specifications** automatically. The system should also decide **which type of UML or architecture diagram** best fits the input.

Architectural doc files may contain high-level system descriptions, component interactions, sequences, flows, modules, etc. Based on this, the app should automatically determine if a class diagram, component diagram, sequence diagram, deployment diagram, use case diagram, or activity diagram is appropriate.

The output must be:
1. The **chosen UML/diagram type**
2. A **PlantUML text specification**
3. Rendering of the PlantUML into an image (optional but preferred)

## Requirements

### Core Functionality
1. **Input Handling**
   - Accept source code files (multiple languages)
   - Accept .docx documents (extract text with structure)
   - Accept pasted code/text via REST API or CLI

2. **Analysis & Decision Making**
   - Use OpenAI API to send the input to an LLM
   - The LLM should:
     a. Determine which UML/diagram type is appropriate
     b. Extract entities, actors, modules, relationships, flows, etc.
     c. Produce a **PlantUML diagram text**
   - The prompt to the LLM must guide it to return:
     ```
     {
       "diagram_type": "...",
       "plantuml": "@startuml ... @enduml"
     }
     ```

3. **PlantUML Integration**
   - Use local PlantUML CLI or a PlantUML server to convert PlantUML text into an image (PNG/SVG)
   - Save or return the image

4. **APIs & Interfaces**
   - REST API (e.g., Express/FastAPI) that accepts:
     - Code files
     - .docx uploads
   - CLI tool that accepts a code file or docx path

5. **Modular Design**
   - `input_parser` (handles file uploads & text extraction)
   - `openai_service` (talks to OpenAI, performs classification + extraction + generation)
   - `plantuml_generator` (builds PlantUML text)
   - `renderer` (runs PlantUML)
   - `server` (REST API)
   - `cli` (command line interface)

6. **Comments & Documentation**
   - Generate clear comments
   - Provide example usage in README
   - Provide sample tests

## Prompts for LLM (in code)
When calling the OpenAI API to generate the diagram, use a prompt format like:

"""
You are an AI architect assistant.

Input text or code:

<INSERT CODE OR TEXT FROM DOCX>

Task 1: Analyze the input and decide which diagram type best represents the relationships and structure. Valid choices:
- class
- component
- sequence
- deployment
- activity
- use case

Task 2: Identify the entities, modules, actors, interactions, dependencies, and flows described.

Task 3: Output a JSON with keys:
- diagram_type
- plantuml

The value of plantuml should contain the correct PlantUML specification between @startuml and @enduml for the chosen diagram type with all relationships and elements described.

Only output valid JSON. Example output format:
{
  "diagram_type": "component",
  "plantuml": "@startuml\n(...diagram contents...)\n@enduml"
}
"""

## Example Invocation
Provide example using cURL or HTTP client to test diagram generation via the REST API.

## Bonus Features (Optional)
- Support multiple diagrams per document
- LLM validation of PlantUML correctness
- Diagram style options (e.g., color, layout hints)