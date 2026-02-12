"""Async PostgreSQL connection pool and schema bootstrap.

Thin wrapper around ``db.connection`` — keeps the existing import paths
(``from .services import db``) working while the canonical pool logic
lives in ``packages/core/src/db/connection.py``.
"""

from ..db.connection import (  # noqa: F401
    close,
    connect,
    execute,
    fetch_all,
    fetch_one,
    get_pool,
    health_check,
)
