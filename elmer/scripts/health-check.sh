#!/usr/bin/env bash
set -euo pipefail

# Load env if available
if [ -f .env ]; then
    set -a; source .env; set +a
fi

CORE_HOST="${ELMER_CORE_HOST:-localhost}"
CORE_PORT="${ELMER_CORE_PORT:-8100}"
WORKER_HOST="${ELMER_WORKER_HOST:-localhost}"
WORKER_PORT="${ELMER_WORKER_PORT:-8101}"

echo "=== Elmer Health Check ==="
echo ""

check_service() {
    local name="$1"
    local url="$2"
    if curl -sf --max-time 3 "$url" > /dev/null 2>&1; then
        echo "  [OK]   $name"
    else
        echo "  [FAIL] $name ($url)"
    fi
}

check_service "Core API"       "http://${CORE_HOST}:${CORE_PORT}/health"
check_service "Dashboard"      "http://${CORE_HOST}:8501"
check_service "Worker"         "http://${WORKER_HOST}:${WORKER_PORT}/health"
# MQTT is not HTTP — use a TCP port check instead of curl
MQTT_HOST="${MQTT_HOST:-localhost}"
MQTT_PORT="${MQTT_PORT:-1883}"
if nc -z "$MQTT_HOST" "$MQTT_PORT" 2>/dev/null; then
    echo "  [OK]   MQTT"
else
    echo "  [FAIL] MQTT (${MQTT_HOST}:${MQTT_PORT})"
fi
check_service "Ollama"         "http://${OLLAMA_HOST:-localhost}:${OLLAMA_PORT:-11434}/api/tags"

echo ""
echo "Docker containers:"
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "  Docker compose not running."
