You are responsible for integrating Mermaid diagram rendering via Docker into the system.

When a diagram generation request arrives that should be rendered with Mermaid (e.g., sequence, flow, story, or other mermaid-type diagrams), you must:

1) Create a temporary `.mmd` file containing the Mermaid syntax generated from IR.
2) Use the official Docker-ized Mermaid CLI to render this file to SVG.
   - The Docker image to use is `minlag/mermaid-cli`, which contains mmdc, the Mermaid CLI tool.  [oai_citation:0‡hub.docker.com](https://hub.docker.com/r/minlag/mermaid-cli?utm_source=chatgpt.com)
3) Run the container in a reproducible way, mounting the local directory as `/data`, and using `mmdc -i` and `-o` to convert `.mmd` → `.svg`.

Your code should run a command similar to:

"""bash
docker run --rm -v $(pwd):/data minlag/mermaid-cli \
  -i /data/<input_filename>.mmd \
  -o /data/<output_filename>.svg
"""

Replace `<input_filename>` and `<output_filename>` appropriately each time.

Important:
- Use absolute paths when mounting into Docker to ensure the file is accessible.  [oai_citation:1‡Stack Overflow](https://stackoverflow.com/questions/74086698/mermaid-cli-input-file-data-diagram-mmd-doesnt-exist?utm_source=chatgpt.com)
- Always include `--rm` to remove the container after rendering.
- Do not rely on any external network or installed Node.js — this runs fully in Docker.
- Output must be a valid SVG that can be inlined or post-processed for styling/animation.

Structure the logic so that:
- If the rendering succeeds, return the path to the generated SVG.
- If rendering fails, capture stderr and include it in the audit/logging for debugging.

Test this integration by running:
- a basic Mermaid flowchart
- sequence diagram
- complex diagram spanning services

The agent’s output should include the Docker run command it executed for traceability, and the final SVG path for use in the application.