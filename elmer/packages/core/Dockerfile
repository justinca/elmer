FROM python:3.11-slim

WORKDIR /app

# Install dependencies for both common and core.
COPY packages/common/requirements.txt /tmp/common-requirements.txt
COPY packages/core/requirements.txt /tmp/core-requirements.txt
RUN pip install --no-cache-dir -r /tmp/common-requirements.txt -r /tmp/core-requirements.txt

# Copy shared common package and core source.
COPY packages/common/ /app/packages/common/
COPY packages/core/src/ /app/src/

ENV PYTHONPATH=/app/packages

EXPOSE 8100

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8100"]
