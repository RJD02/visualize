FROM openjdk:17-jdk-slim
WORKDIR /app
# Structurizr CLI would be added here. This is a scaffold for the POC.
# The final image should provide a CLI that accepts DSL or workspace JSON and outputs SVG.
CMD ["sh", "-c", "echo Structurizr scaffold"]
FROM structurizr/cli:latest

COPY render.sh /render.sh
RUN chmod +x /render.sh

ENTRYPOINT ["/render.sh"]
