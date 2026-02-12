FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY agent_definitions/ ./agent_definitions/

CMD ["python", "-m", "src.orchestrator"]
