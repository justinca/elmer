FROM python:3.11-slim

WORKDIR /app

# Copy package sources.
COPY packages/common/ /app/packages/common/
COPY packages/core/ /app/packages/core/

# Install common first (core depends on it), then core.
RUN pip install --no-cache-dir /app/packages/common/ /app/packages/core/

EXPOSE 8100

CMD ["uvicorn", "elmer_core.main:app", "--host", "0.0.0.0", "--port", "8100"]
