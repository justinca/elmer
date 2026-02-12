#!/usr/bin/env bash
# ============================================================
# Elmer — Deploy Script
# Pulls latest code, runs migrations, builds and restarts
# changed services, then prints a status summary.
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

# Colour helpers
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

echo "============================================"
echo "  Elmer — Deploy"
echo "============================================"
echo ""

# ----------------------------------------------------------
# 1. Pull latest from git
# ----------------------------------------------------------
info "Pulling latest changes..."
if ! git pull --ff-only; then
    err "git pull failed — resolve conflicts before deploying."
    exit 1
fi
echo ""

# ----------------------------------------------------------
# 2. Run database migrations
# ----------------------------------------------------------
info "Running database migrations..."
if bash scripts/init-db.sh; then
    info "Database is up to date."
else
    warn "Database migration had issues (non-fatal). Check output above."
fi
echo ""

# ----------------------------------------------------------
# 3. Build and restart changed services
# ----------------------------------------------------------
info "Building containers..."
docker compose build

info "Starting services (only changed containers restart)..."
docker compose up -d
echo ""

# ----------------------------------------------------------
# 4. Wait for Core to become healthy
# ----------------------------------------------------------
info "Waiting for elmer-core to become healthy..."
MAX_WAIT=60
INTERVAL=5
ELAPSED=0

while [ $ELAPSED -lt $MAX_WAIT ]; do
    if curl -sf --max-time 3 http://localhost:8100/health > /dev/null 2>&1; then
        info "elmer-core is healthy."
        break
    fi
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    warn "elmer-core did not become healthy within ${MAX_WAIT}s."
    warn "Check logs:  docker compose logs elmer-core"
fi
echo ""

# ----------------------------------------------------------
# 5. Status summary
# ----------------------------------------------------------
info "=== Deploy Summary ==="
echo ""

docker compose ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null || true
echo ""

bash scripts/health-check.sh 2>/dev/null || true

echo ""
info "Deploy complete."
