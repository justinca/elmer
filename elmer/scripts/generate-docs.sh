#!/usr/bin/env bash
set -euo pipefail

# Load env if available
if [ -f .env ]; then
    set -a; source .env; set +a
fi

CORE_HOST="${ELMER_CORE_HOST:-localhost}"
CORE_PORT="${ELMER_CORE_PORT:-8100}"
BASE_URL="http://${CORE_HOST}:${CORE_PORT}"

echo "=== Elmer Auto-Documentation Generator ==="
echo ""
echo "Triggering doc generation at ${BASE_URL}/docs/generate ..."

RESPONSE=$(curl -sf --max-time 30 "${BASE_URL}/docs/generate")

if [ $? -ne 0 ] || [ -z "$RESPONSE" ]; then
    echo "  [FAIL] Could not reach Core API at ${BASE_URL}"
    exit 1
fi

python3 -c "
import json, sys
data = json.loads('''${RESPONSE}''')
print(f\"  Generated at: {data['generated_at']}\")
print(f\"  Duration:     {data['duration_seconds']}s\")
print(f\"  Changes:      {data['changes_detected']}\")
print(f\"  Files written:\")
for f in data['files_written']:
    print(f'    - {f}')
"

echo ""
echo "Done."
