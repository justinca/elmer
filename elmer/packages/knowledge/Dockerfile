FROM python:3.11-slim

WORKDIR /app

# Copy package sources (context is repo root).
COPY packages/common/ /app/packages/common/
COPY packages/knowledge/ /app/packages/knowledge/

# Install common first, then knowledge deps.
RUN pip install --no-cache-dir /app/packages/common/ \
    && pip install --no-cache-dir -r /app/packages/knowledge/requirements.txt

COPY packages/knowledge/src/ /app/src/

CMD ["python", "-m", "src.scheduler"]
