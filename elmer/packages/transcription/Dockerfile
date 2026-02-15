FROM python:3.11-slim

WORKDIR /app

# Copy package sources (context is repo root).
COPY packages/common/ /app/packages/common/
COPY packages/transcription/ /app/packages/transcription/

# Install common first, then transcription deps.
RUN pip install --no-cache-dir /app/packages/common/ \
    && pip install --no-cache-dir -r /app/packages/transcription/requirements.txt

COPY packages/transcription/src/ /app/src/

CMD ["python", "-m", "src.watcher"]
