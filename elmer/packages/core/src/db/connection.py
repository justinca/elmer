"""Async PostgreSQL connection pool with helpers.

Provides a singleton pool manager used by all Elmer services.  The pool
is created lazily on first call to ``connect()`` and tolerates a missing
database at startup so the rest of the application can still run.

Embedding dimension is 768 (nomic-embed-text via Ollama).
"""

import asyncio
import logging
import pathlib
from typing import Any

import asyncpg

from ..config import settings

logger = logging.getLogger("elmer.db")

_pool: asyncpg.Pool | None = None

RETRY_INTERVAL = 5   # seconds between connection attempts
POOL_MIN_SIZE = 2
POOL_MAX_SIZE = 10

_INIT_SQL = (pathlib.Path(__file__).parent / "init.sql").read_text()


# ------------------------------------------------------------------
# Pool lifecycle
# ------------------------------------------------------------------

async def connect(max_retries: int = 3) -> asyncpg.Pool | None:
    """Create the connection pool and bootstrap the schema.

    Returns the pool on success or ``None`` if Postgres is unreachable
    after *max_retries* attempts.
    """
    global _pool

    for attempt in range(1, max_retries + 1):
        try:
            _pool = await asyncpg.create_pool(
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                database=settings.POSTGRES_DB,
                min_size=POOL_MIN_SIZE,
                max_size=POOL_MAX_SIZE,
            )
            logger.info(
                "Connected to PostgreSQL at %s:%s/%s",
                settings.POSTGRES_HOST,
                settings.POSTGRES_PORT,
                settings.POSTGRES_DB,
            )
            await _bootstrap_schema()
            return _pool
        except (OSError, asyncpg.PostgresError) as exc:
            logger.warning(
                "PostgreSQL attempt %d/%d failed: %s",
                attempt, max_retries, exc,
            )
            if attempt < max_retries:
                await asyncio.sleep(RETRY_INTERVAL)

    logger.error(
        "Could not connect to PostgreSQL after %d attempts — "
        "running without database.",
        max_retries,
    )
    return None


async def close() -> None:
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL connection pool closed.")


def get_pool() -> asyncpg.Pool | None:
    """Return the current pool (may be ``None`` if not connected)."""
    return _pool


# ------------------------------------------------------------------
# Query helpers
# ------------------------------------------------------------------

async def execute(query: str, *args: Any) -> str:
    """Execute a statement and return the status string."""
    if _pool is None:
        raise RuntimeError("Database pool is not initialised")
    async with _pool.acquire() as conn:
        return await conn.execute(query, *args)


async def fetch_one(query: str, *args: Any) -> asyncpg.Record | None:
    """Fetch a single row, or ``None`` if no rows match."""
    if _pool is None:
        raise RuntimeError("Database pool is not initialised")
    async with _pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def fetch_all(query: str, *args: Any) -> list[asyncpg.Record]:
    """Fetch all matching rows."""
    if _pool is None:
        raise RuntimeError("Database pool is not initialised")
    async with _pool.acquire() as conn:
        return await conn.fetch(query, *args)


# ------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------

async def health_check() -> dict[str, Any]:
    """Return connection health info (for /health endpoints)."""
    if _pool is None:
        return {"status": "disconnected", "pool_size": 0}

    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 AS ok, now() AS server_time")
        return {
            "status": "connected",
            "pool_size": _pool.get_size(),
            "pool_free": _pool.get_idle_size(),
            "server_time": str(row["server_time"]) if row else None,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# ------------------------------------------------------------------
# Internal
# ------------------------------------------------------------------

async def _bootstrap_schema() -> None:
    """Run init.sql to create extensions, schema, and tables."""
    if _pool is None:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(_INIT_SQL)
        logger.info("Database schema bootstrapped.")
    except asyncpg.PostgresError:
        logger.exception("Failed to bootstrap database schema.")
