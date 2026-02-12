#!/usr/bin/env bash
# ============================================================
# Elmer — Migrate embedding columns from vector(1536) to vector(768)
#
# Safe to run multiple times (idempotent). Checks current dimension
# before altering and only acts if a change is needed.
#
# Usage:  ./scripts/migrate-vectors.sh
# ============================================================

set -euo pipefail

DB_HOST="${POSTGRES_HOST:-127.0.0.1}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_NAME="${POSTGRES_DB:-elmer}"

TARGET_DIM=768

echo "=== Elmer Vector Migration ==="
echo "Target dimension: ${TARGET_DIM}"
echo "Database: ${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
echo ""

PSQL="psql -h ${DB_HOST} -p ${DB_PORT} -U ${DB_USER} -d ${DB_NAME} -v ON_ERROR_STOP=1"

# Helper: get current vector dimension for a column.
get_dim() {
    local table=$1
    local column=${2:-embedding}
    ${PSQL} -tAc "
        SELECT atttypmod
        FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = 'elmer'
          AND c.relname = '${table}'
          AND a.attname = '${column}';
    " 2>/dev/null || echo "0"
}

# Helper: migrate a single table's embedding column.
migrate_table() {
    local table=$1
    local current_dim
    current_dim=$(get_dim "${table}")

    # atttypmod for vector(N) = N + 4 in some pg versions, or just N.
    # We check if it already matches.
    if [ "${current_dim}" = "${TARGET_DIM}" ]; then
        echo "  ✓ elmer.${table}.embedding is already vector(${TARGET_DIM})"
        return 0
    fi

    echo "  → Altering elmer.${table}.embedding to vector(${TARGET_DIM})..."

    # Clear existing embeddings (they're the wrong dimension).
    ${PSQL} -c "UPDATE elmer.${table} SET embedding = NULL WHERE embedding IS NOT NULL;" 2>/dev/null || true

    # Alter the column type.
    ${PSQL} -c "ALTER TABLE elmer.${table} ALTER COLUMN embedding TYPE vector(${TARGET_DIM});"

    echo "  ✓ elmer.${table}.embedding migrated to vector(${TARGET_DIM})"
}

# Helper: recreate ivfflat index for a table.
recreate_index() {
    local table=$1
    local idx_name="idx_${table}_embedding"

    echo "  → Recreating index ${idx_name}..."
    ${PSQL} -c "DROP INDEX IF EXISTS elmer.${idx_name};"
    ${PSQL} -c "CREATE INDEX ${idx_name} ON elmer.${table} USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
    echo "  ✓ Index ${idx_name} created"
}

echo "--- Migrating tables ---"
echo ""

for table in documents notes transcriptions; do
    echo "[elmer.${table}]"
    migrate_table "${table}"
    recreate_index "${table}"
    echo ""
done

echo "=== Migration complete ==="
