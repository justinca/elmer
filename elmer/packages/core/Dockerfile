FROM python:3.11-slim

WORKDIR /app

# Copy package sources.
COPY packages/common/ /app/packages/common/
COPY packages/agents/ /app/packages/agents/
COPY packages/core/ /app/packages/core/

# Copy agent definitions (YAML) for startup sync.
COPY packages/agents/agent_definitions/ /app/agent_definitions/

# Install common, agents, then core.
RUN pip install --no-cache-dir /app/packages/common/ /app/packages/agents/ /app/packages/core/

EXPOSE 8100

CMD ["uvicorn", "elmer_core.main:app", "--host", "0.0.0.0", "--port", "8100"]
