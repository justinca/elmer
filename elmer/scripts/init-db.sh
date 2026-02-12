#!/usr/bin/env bash
# ============================================================
# Elmer — Database Initialisation Script
# Connects to the native PostgreSQL instance on localhost.
# Tries peer auth (sudo -u postgres psql) first, then falls
# back to password auth via PGPASSWORD.
# Safe to run multiple times (all statements are IF NOT EXISTS).
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Load .env if present
if [[ -f "$REPO_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_DIR/.env"
    set +a
fi

POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD-}"
POSTGRES_DB="${POSTGRES_DB:-elmer}"

INIT_SQL="$REPO_DIR/packages/core/src/db/init.sql"

# Colour helpers
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ----------------------------------------------------------
# Decide connection method: peer auth or password auth
# ----------------------------------------------------------
USE_PEER=false

if sudo -n -u postgres psql -d postgres -c '\q' 2>/dev/null; then
    USE_PEER=true
    info "Using peer auth (sudo -u postgres psql)."
else
    info "Peer auth unavailable; using password auth."
fi

run_psql() {
    if $USE_PEER; then
        sudo -u postgres psql "$@"
    else
        PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" "$@"
    fi
}

# ----------------------------------------------------------
# 1. Check that we can reach PostgreSQL
# ----------------------------------------------------------
info "Checking PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT} ..."

if ! command -v psql &>/dev/null; then
    err "psql not found.  Install postgresql-client."
    exit 1
fi

if ! run_psql -d postgres -c '\q' 2>/dev/null; then
    err "Cannot connect to PostgreSQL.  Is the server running?"
    err "If using password auth, set POSTGRES_PASSWORD in .env"
    exit 1
fi

info "PostgreSQL is reachable."

# ----------------------------------------------------------
# 2. Check for pgvector extension
# ----------------------------------------------------------
info "Checking for pgvector extension ..."

HAS_VECTOR=$(run_psql -d postgres \
    -tAc "SELECT 1 FROM pg_available_extensions WHERE name = 'vector';" 2>/dev/null || true)

if [[ "$HAS_VECTOR" != "1" ]]; then
    warn "pgvector extension is NOT available in this PostgreSQL instance."
    warn "Install it with:  sudo apt install postgresql-14-pgvector"
    exit 1
fi

info "pgvector extension is available."

# ----------------------------------------------------------
# 3. Create the elmer database if it doesn't exist
# ----------------------------------------------------------
info "Ensuring database '${POSTGRES_DB}' exists ..."

DB_EXISTS=$(run_psql -d postgres \
    -tAc "SELECT 1 FROM pg_database WHERE datname = '${POSTGRES_DB}';" 2>/dev/null || true)

if [[ "$DB_EXISTS" != "1" ]]; then
    info "Creating database '${POSTGRES_DB}' ..."
    run_psql -d postgres -c "CREATE DATABASE ${POSTGRES_DB};"
    info "Database created."
else
    info "Database '${POSTGRES_DB}' already exists."
fi

# ----------------------------------------------------------
# 4. Run init.sql
# ----------------------------------------------------------
if [[ ! -f "$INIT_SQL" ]]; then
    err "Schema file not found: $INIT_SQL"
    exit 1
fi

info "Running schema migration ..."
run_psql -d "$POSTGRES_DB" -f "$INIT_SQL"

info "Schema migration complete."

# ----------------------------------------------------------
# 5. Summary
# ----------------------------------------------------------
echo ""
info "=== Database Initialisation Summary ==="
echo ""

TABLES=$(run_psql -d "$POSTGRES_DB" \
    -tAc "SELECT tablename FROM pg_tables WHERE schemaname = 'elmer' ORDER BY tablename;")

echo "  Database:   ${POSTGRES_DB}"
echo "  Schema:     elmer"
echo "  Extension:  vector (pgvector)"
echo ""
echo "  Tables:"
while IFS= read -r table; do
    if [[ -n "$table" ]]; then
        COUNT=$(run_psql -d "$POSTGRES_DB" \
            -tAc "SELECT count(*) FROM elmer.${table};" 2>/dev/null || echo "?")
        echo "    - elmer.${table}  (${COUNT} rows)"
    fi
done <<< "$TABLES"

echo ""
info "Done.  Elmer database is ready."
