Goal
Build a conversational, agent-driven architecture visualization platform.

The system must accept source code and architecture documents, reason about them,
generate architecture images, and allow users to iteratively refine and reason
about those images through natural conversation.

The system should feel like:

ChatGPT for architecture diagrams
Figma-like iteration, but via conversation
Safe, architecture-aware, and stateful
Implementation details (schemas, table structures, API contracts) should be
designed by you unless explicitly constrained.

Core Capabilities
Input Understanding
Accept code and architecture documents (PDF, DOCX, MD, raw text)
Automatically reason about what kind of system the input represents
Generate an initial architecture visualization
Conversational Interaction
Provide a chat-based interface where users can:
Ask questions about the diagram
Reason about architectural choices
Request visual changes to the diagram
Conversation must be stateful and tied to a session
Iterative Image Editing
Images must be versioned and persisted
Each edit produces a new image version
Users should be able to refer to images explicitly in conversation
(e.g., “in image #3, group services by domain”)
Edits should preserve architectural correctness unless explicitly regenerated
Reasoning over Conversation
The system must interpret user messages and decide:
Whether the user wants an explanation
Whether the user wants an image edit
Whether clarification is required
You may use an additional LLM call to interpret conversation intent if needed
Persistence & Referencing
Use PostgreSQL to store:
Sessions
Images
Image metadata (version, parent image, creation reason)
Conversation history
Each image must have a stable ID so it can be referenced in chat
UI Requirements (React + TailwindCSS)
Build a modern, polished UI using React and TailwindCSS
UI must be conversational-first
Required UI Areas
Upload/Input Area

Upload files or paste text
Trigger initial generation
Diagram Viewer

Display current image
Zoom and pan
Show image version and ID
Allow switching between image versions
Conversation Panel

Chat-style interface
User messages drive reasoning and edits
System messages explain actions taken
Assistant messages explain architectural reasoning
The UI should feel responsive, clean, and professional.

Backend & Server Requirements
Upgrade the server to support:
Multiple APIs (LLM, image generation, diagram rendering)
Session-based workflows
Concurrent users
The server must orchestrate:
Architecture reasoning
Image generation
Image editing
Conversation handling
Server must expose APIs suitable for a conversational UI
You may choose:

Node.js / TypeScript
Any reasonable web framework
Any LLM provider(s)
Any image generation approach
Workflow Expectations
The system should:

Ingest input
Reason about architecture
Generate an initial diagram image
Persist the image and metadata
Enter conversational mode
Interpret each user message
Decide whether to:
Explain
Edit an existing image
Generate a new image
Persist results and update the UI
This loop continues until the session ends.

Design Principles
Conversational interaction is the primary interface
Images are stateful artifacts, not one-off outputs
Reasoning and rendering must be separated
The system should be extensible (new agents, new renderers)
The UX should encourage exploration and iteration
Non-Goals
Do not hard-code prompts in the UI
Do not treat each message as stateless
Do not discard old images
Do not require users to understand UML or tooling details
Deliverables
React UI using TailwindCSS
Backend server supporting conversational workflows
PostgreSQL integration for images and metadata
Image versioning and referencing by ID
End-to-end flow from input → conversation → iterative visualization
Clear README explaining the system architecture and usage
Use the following tech stack:
python + sqlalchems + fastAPI + react + tailwindcss

Scoping new project set