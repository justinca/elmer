"""Async PostgreSQL connection pool and schema bootstrap.

Handles database unavailability gracefully — the app starts even if
Postgres is down and logs warnings until the connection succeeds.
"""

import asyncio
import logging

import asyncpg

from ..config import settings

logger = logging.getLogger("elmer.db")

pool: asyncpg.Pool | None = None

RETRY_INTERVAL = 5  # seconds between connection attempts

_BOOTSTRAP_SQL = """
CREATE SCHEMA IF NOT EXISTS elmer;

CREATE TABLE IF NOT EXISTS elmer.nodes (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    host        TEXT NOT NULL DEFAULT '',
    port        INTEGER NOT NULL DEFAULT 0,
    last_seen   TIMESTAMPTZ,
    status      TEXT NOT NULL DEFAULT 'unknown',
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS elmer.events (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    source      TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    data        JSONB NOT NULL DEFAULT '{}'::jsonb
);
"""


async def connect(max_retries: int = 3) -> asyncpg.Pool | None:
    """Create the connection pool with retries.

    Returns the pool on success, or ``None`` if the database is
    unreachable after *max_retries* attempts.
    """
    global pool

    for attempt in range(1, max_retries + 1):
        try:
            pool = await asyncpg.create_pool(
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                database=settings.POSTGRES_DB,
                min_size=2,
                max_size=10,
            )
            logger.info(
                "Connected to PostgreSQL at %s:%s/%s",
                settings.POSTGRES_HOST,
                settings.POSTGRES_PORT,
                settings.POSTGRES_DB,
            )
            await _bootstrap_schema()
            return pool
        except (OSError, asyncpg.PostgresError) as exc:
            logger.warning(
                "PostgreSQL connection attempt %d/%d failed: %s",
                attempt,
                max_retries,
                exc,
            )
            if attempt < max_retries:
                await asyncio.sleep(RETRY_INTERVAL)

    logger.error(
        "Could not connect to PostgreSQL after %d attempts — "
        "running without database.",
        max_retries,
    )
    return None


async def _bootstrap_schema():
    """Create the elmer schema and tables if they don't exist."""
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        logger.info("Database schema bootstrapped.")
    except asyncpg.PostgresError:
        logger.exception("Failed to bootstrap database schema.")


async def close():
    """Close the connection pool."""
    global pool
    if pool is not None:
        await pool.close()
        pool = None
        logger.info("PostgreSQL connection pool closed.")
