"""Log4OM read-only SQLite endpoints — QSO queries, stats, DXCC, contests.

The Log4OM database schema varies between versions.  On first connect
this module introspects the schema and builds an adaptive column mapping
so queries work regardless of column naming conventions.

IMPORTANT: All access is strictly read-only.  The database is opened
with ``?mode=ro`` to guarantee no writes can occur.
"""

import logging
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator

from fastapi import APIRouter, HTTPException, Query

from ..config import settings

router = APIRouter()
logger = logging.getLogger("elmer.worker.log4om")

# ---------------------------------------------------------------------------
# Schema introspection
# ---------------------------------------------------------------------------

# Candidates for each logical column — tried in order, first match wins.
_COLUMN_CANDIDATES: dict[str, list[str]] = {
    "call":       ["Call", "CALL", "call", "Callsign", "CALLSIGN", "callsign"],
    "band":       ["Band", "BAND", "band"],
    "mode":       ["Mode", "MODE", "mode", "SubMode"],
    "submode":    ["SubMode", "SUBMODE", "submode", "Sub_Mode"],
    "freq":       ["Freq", "FREQ", "freq", "Frequency", "FREQUENCY"],
    "qso_date":   ["QSODate", "QSO_DATE", "qso_date", "QSO_Date",
                   "ContactDate", "Date", "DATE", "qsodate"],
    "qso_end":    ["QSOEndDate", "qsoenddate"],
    "time_on":    ["TimeOn", "TIME_ON", "time_on", "Time_On",
                   "ContactTime", "Time", "TIME"],
    "rst_sent":   ["RSTSent", "RST_SENT", "rst_sent", "RST_Sent", "rstsent"],
    "rst_rcvd":   ["RSTRcvd", "RST_RCVD", "rst_rcvd", "RST_Rcvd", "rstrcvd"],
    "grid":       ["GridSquare", "Gridsquare", "GRIDSQUARE", "grid",
                   "Grid", "GRID", "gridsquare"],
    "country":    ["Country", "COUNTRY", "country", "DXCC_Country",
                   "DXCCCountry"],
    "comment":    ["Comment", "COMMENT", "comment", "Notes", "NOTES",
                   "QSO_Notes", "notes"],
    "contest":    ["Contest", "CONTEST", "contest", "ContestID",
                   "Contest_ID", "ContestName", "contestid"],
    "name":       ["Name", "NAME", "name", "ContactName", "Contact_Name"],
    "qsl_sent":   ["QSLSent", "QSL_SENT", "qsl_sent", "QSL_Sent"],
    "qsl_rcvd":   ["QSLRcvd", "QSL_RCVD", "qsl_rcvd", "QSL_Rcvd"],
    "qsl_status": ["qsoconfirmations", "QSOConfirmations"],
    "lotw_sent":  ["LOTWSent", "LOTW_SENT", "lotw_sent", "LoTWSent",
                   "LOTW_Sent"],
    "lotw_rcvd":  ["LOTWRcvd", "LOTW_RCVD", "lotw_rcvd", "LoTWRcvd",
                   "LOTW_Rcvd"],
    "dxcc":       ["DXCC", "dxcc", "DXCCEntity", "DXCC_Entity"],
    "continent":  ["Continent", "CONTINENT", "continent", "Cont", "CONT",
                   "cont"],
    "cq_zone":    ["CQZone", "CQ_ZONE", "cq_zone", "CQZ", "cqzone"],
    "itu_zone":   ["ITUZone", "ITU_ZONE", "itu_zone", "ituzone"],
    "state":      ["State", "STATE", "state", "US_State"],
    "county":     ["County", "COUNTY", "county", "cnty"],
    "power":      ["Power", "POWER", "power", "TX_Power", "TXPower", "txpwr"],
    "antenna":    ["Antenna", "ANTENNA", "antenna", "MyAntenna"],
    "operator":   ["Operator", "OPERATOR", "operator", "StationCallsign",
                   "stationcallsign"],
    "qth":        ["QTH", "qth"],
    "pfx":        ["Prefix", "PFX", "pfx"],
}

# Table name candidates (tried in order).
_TABLE_CANDIDATES = [
    "LogTable", "log_table", "LOG", "Log", "QSOLog",
    "log", "LOGTABLE", "Logbook", "logbook",
]


@dataclass
class SchemaMap:
    """Mapping between logical column names and actual database columns."""
    table_name: str
    columns: dict[str, str] = field(default_factory=dict)
    all_columns: list[str] = field(default_factory=list)


_schema_cache: SchemaMap | None = None


def _introspect_schema(conn: sqlite3.Connection) -> SchemaMap:
    """Discover the log table and build column mapping."""
    global _schema_cache
    if _schema_cache is not None:
        return _schema_cache

    # Find all tables.
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    tables = [row[0] for row in cursor.fetchall()]

    if not tables:
        raise RuntimeError("Database has no tables")

    # Find the log table.
    log_table: str | None = None
    for candidate in _TABLE_CANDIDATES:
        if candidate in tables:
            log_table = candidate
            break

    if log_table is None:
        for t in tables:
            if "log" in t.lower():
                log_table = t
                break

    if log_table is None:
        # Last resort: pick the largest table.
        max_count = -1
        for t in tables:
            try:
                row = conn.execute(f'SELECT count(*) FROM "{t}"').fetchone()
                if row and row[0] > max_count:
                    max_count = row[0]
                    log_table = t
            except sqlite3.OperationalError:
                continue

    if log_table is None:
        raise RuntimeError(f"No log table found. Tables: {tables}")

    # Get column info.
    cursor = conn.execute(f'PRAGMA table_info("{log_table}")')
    actual_cols = [row[1] for row in cursor.fetchall()]
    actual_set = set(actual_cols)

    # Map logical names to actual columns.
    column_map: dict[str, str] = {}
    for logical, candidates in _COLUMN_CANDIDATES.items():
        for c in candidates:
            if c in actual_set:
                column_map[logical] = c
                break

    schema = SchemaMap(
        table_name=log_table,
        columns=column_map,
        all_columns=actual_cols,
    )
    _schema_cache = schema

    logger.info(
        "Log4OM schema: table=%s, mapped %d/%d columns",
        log_table, len(column_map), len(_COLUMN_CANDIDATES),
    )
    logger.debug("Column mapping: %s", column_map)

    return schema


def _reset_schema_cache() -> None:
    """Clear the cached schema (for testing or schema changes)."""
    global _schema_cache
    _schema_cache = None


# ---------------------------------------------------------------------------
# SQLite connection management
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.5


@contextmanager
def _get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Open a read-only SQLite connection with retry on lock."""
    db_path = settings.ELMER_LOG4OM_DB_PATH
    if not db_path:
        raise HTTPException(
            status_code=503,
            detail="ELMER_LOG4OM_DB_PATH not configured",
        )

    path = Path(db_path)
    if not path.is_file():
        raise HTTPException(
            status_code=503,
            detail=f"Log4OM database not found: {db_path}",
        )

    uri = f"file:{path}?mode=ro"
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=5.0)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()
            return
        except sqlite3.OperationalError as exc:
            last_error = exc
            if "locked" in str(exc).lower() and attempt < _MAX_RETRIES - 1:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Database locked, retry %d/%d in %.1fs",
                    attempt + 1, _MAX_RETRIES, delay,
                )
                time.sleep(delay)
            else:
                raise HTTPException(
                    status_code=503,
                    detail=f"Log4OM database unavailable: {exc}",
                )

    raise HTTPException(
        status_code=503,
        detail=f"Log4OM database locked after {_MAX_RETRIES} retries: {last_error}",
    )


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _col(schema: SchemaMap, logical: str) -> str | None:
    """Get the actual column name for a logical name, or None."""
    return schema.columns.get(logical)


def _select_clause(schema: SchemaMap, logical_names: list[str]) -> str:
    """Build a SELECT clause mapping logical names to actual columns."""
    parts = []
    for ln in logical_names:
        actual = _col(schema, ln)
        if actual:
            parts.append(f'"{actual}" AS "{ln}"')
    return ", ".join(parts) if parts else "*"


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a Row to a plain dict."""
    return {k: row[k] for k in row.keys()}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
async def log4om_status():
    """Check Log4OM database connectivity and schema info."""
    with _get_connection() as conn:
        schema = _introspect_schema(conn)

        count_row = conn.execute(
            f'SELECT count(*) AS cnt FROM "{schema.table_name}"'
        ).fetchone()
        total = count_row["cnt"] if count_row else 0

        newest = None
        date_col = _col(schema, "qso_date")
        if date_col:
            row = conn.execute(
                f'SELECT "{date_col}" AS d FROM "{schema.table_name}" '
                f'ORDER BY "{date_col}" DESC LIMIT 1'
            ).fetchone()
            newest = row["d"] if row else None

        # List all tables.
        tables = [
            r[0] for r in
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]

    return {
        "status": "ok",
        "db_path": settings.ELMER_LOG4OM_DB_PATH,
        "table_name": schema.table_name,
        "mapped_columns": schema.columns,
        "all_columns": schema.all_columns,
        "all_tables": tables,
        "total_qsos": total,
        "newest_qso": newest,
    }


@router.get("/qsos")
async def get_qsos(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    call: str | None = Query(default=None),
    band: str | None = Query(default=None),
    mode: str | None = Query(default=None),
    country: str | None = Query(default=None),
    since: str | None = Query(default=None, description="ISO date YYYY-MM-DD"),
    until: str | None = Query(default=None, description="ISO date YYYY-MM-DD"),
):
    """Fetch QSOs with optional filters, newest first."""
    with _get_connection() as conn:
        schema = _introspect_schema(conn)

        select_cols = [
            "call", "band", "mode", "freq", "qso_date", "time_on",
            "rst_sent", "rst_rcvd", "grid", "country", "comment",
            "contest", "name", "dxcc", "continent",
        ]
        select = _select_clause(schema, select_cols)
        if not select:
            select = "*"

        conditions: list[str] = []
        params: list[Any] = []

        if call and _col(schema, "call"):
            conditions.append(f'"{_col(schema, "call")}" LIKE ?')
            params.append(f"%{call}%")
        if band and _col(schema, "band"):
            conditions.append(f'"{_col(schema, "band")}" = ?')
            params.append(band)
        if mode and _col(schema, "mode"):
            conditions.append(f'"{_col(schema, "mode")}" LIKE ?')
            params.append(f"%{mode}%")
        if country and _col(schema, "country"):
            conditions.append(f'"{_col(schema, "country")}" LIKE ?')
            params.append(f"%{country}%")
        if since and _col(schema, "qso_date"):
            conditions.append(f'"{_col(schema, "qso_date")}" >= ?')
            params.append(since)
        if until and _col(schema, "qso_date"):
            conditions.append(f'"{_col(schema, "qso_date")}" <= ?')
            params.append(until)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        order_col = _col(schema, "qso_date") or schema.all_columns[0]
        sql = (
            f'SELECT {select} FROM "{schema.table_name}" '
            f'{where} ORDER BY "{order_col}" DESC LIMIT ? OFFSET ?'
        )
        params.extend([limit, offset])

        rows = conn.execute(sql, params).fetchall()
        return [_row_to_dict(r) for r in rows]


@router.get("/qsos/count")
async def get_qso_count(
    call: str | None = Query(default=None),
    band: str | None = Query(default=None),
    mode: str | None = Query(default=None),
    country: str | None = Query(default=None),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
):
    """Total QSO count with optional filters."""
    with _get_connection() as conn:
        schema = _introspect_schema(conn)

        conditions: list[str] = []
        params: list[Any] = []

        if call and _col(schema, "call"):
            conditions.append(f'"{_col(schema, "call")}" LIKE ?')
            params.append(f"%{call}%")
        if band and _col(schema, "band"):
            conditions.append(f'"{_col(schema, "band")}" = ?')
            params.append(band)
        if mode and _col(schema, "mode"):
            conditions.append(f'"{_col(schema, "mode")}" LIKE ?')
            params.append(f"%{mode}%")
        if country and _col(schema, "country"):
            conditions.append(f'"{_col(schema, "country")}" LIKE ?')
            params.append(f"%{country}%")
        if since and _col(schema, "qso_date"):
            conditions.append(f'"{_col(schema, "qso_date")}" >= ?')
            params.append(since)
        if until and _col(schema, "qso_date"):
            conditions.append(f'"{_col(schema, "qso_date")}" <= ?')
            params.append(until)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f'SELECT count(*) AS cnt FROM "{schema.table_name}" {where}'
        row = conn.execute(sql, params).fetchone()
        return {"count": row["cnt"] if row else 0}


@router.get("/stats")
async def get_stats():
    """Aggregate log statistics."""
    with _get_connection() as conn:
        schema = _introspect_schema(conn)
        table = schema.table_name

        # Total QSOs.
        total = conn.execute(
            f'SELECT count(*) AS cnt FROM "{table}"'
        ).fetchone()["cnt"]

        result: dict[str, Any] = {"total_qsos": total}

        # Unique counts.
        call_col = _col(schema, "call")
        if call_col:
            row = conn.execute(
                f'SELECT count(DISTINCT "{call_col}") AS cnt FROM "{table}"'
            ).fetchone()
            result["unique_calls"] = row["cnt"]

        country_col = _col(schema, "country")
        if country_col:
            row = conn.execute(
                f'SELECT count(DISTINCT "{country_col}") AS cnt FROM "{table}" '
                f'WHERE "{country_col}" IS NOT NULL AND "{country_col}" != \'\''
            ).fetchone()
            result["unique_countries"] = row["cnt"]

        grid_col = _col(schema, "grid")
        if grid_col:
            row = conn.execute(
                f'SELECT count(DISTINCT "{grid_col}") AS cnt FROM "{table}" '
                f'WHERE "{grid_col}" IS NOT NULL AND "{grid_col}" != \'\''
            ).fetchone()
            result["unique_grids"] = row["cnt"]

        # QSOs per band.
        band_col = _col(schema, "band")
        if band_col:
            rows = conn.execute(
                f'SELECT "{band_col}" AS band, count(*) AS cnt '
                f'FROM "{table}" WHERE "{band_col}" IS NOT NULL '
                f'GROUP BY "{band_col}" ORDER BY cnt DESC'
            ).fetchall()
            result["qsos_by_band"] = {r["band"]: r["cnt"] for r in rows}

        # QSOs per mode.
        mode_col = _col(schema, "mode")
        if mode_col:
            rows = conn.execute(
                f'SELECT "{mode_col}" AS mode, count(*) AS cnt '
                f'FROM "{table}" WHERE "{mode_col}" IS NOT NULL '
                f'GROUP BY "{mode_col}" ORDER BY cnt DESC'
            ).fetchall()
            result["qsos_by_mode"] = {r["mode"]: r["cnt"] for r in rows}

        # QSOs per year.
        date_col = _col(schema, "qso_date")
        if date_col:
            rows = conn.execute(
                f'SELECT substr("{date_col}", 1, 4) AS year, count(*) AS cnt '
                f'FROM "{table}" WHERE "{date_col}" IS NOT NULL '
                f'GROUP BY year ORDER BY year'
            ).fetchall()
            result["qsos_by_year"] = {r["year"]: r["cnt"] for r in rows}

            # First and last QSO.
            first = conn.execute(
                f'SELECT MIN("{date_col}") AS d FROM "{table}"'
            ).fetchone()
            last = conn.execute(
                f'SELECT MAX("{date_col}") AS d FROM "{table}"'
            ).fetchone()
            result["first_qso"] = first["d"] if first else None
            result["last_qso"] = last["d"] if last else None

        # Top 10 most contacted callsigns.
        if call_col:
            rows = conn.execute(
                f'SELECT "{call_col}" AS call, count(*) AS cnt '
                f'FROM "{table}" WHERE "{call_col}" IS NOT NULL '
                f'GROUP BY "{call_col}" ORDER BY cnt DESC LIMIT 10'
            ).fetchall()
            result["top_calls"] = [
                {"call": r["call"], "count": r["cnt"]} for r in rows
            ]

        return result


@router.get("/dxcc")
async def get_dxcc():
    """DXCC entity summary with band/mode breakdown."""
    with _get_connection() as conn:
        schema = _introspect_schema(conn)
        table = schema.table_name

        country_col = _col(schema, "country")
        if not country_col:
            raise HTTPException(
                status_code=501,
                detail="Country column not found in Log4OM schema",
            )

        band_col = _col(schema, "band")
        mode_col = _col(schema, "mode")
        lotw_rcvd_col = _col(schema, "lotw_rcvd")
        qsl_rcvd_col = _col(schema, "qsl_rcvd")

        # Get all entities with counts.
        rows = conn.execute(
            f'SELECT "{country_col}" AS country, count(*) AS cnt '
            f'FROM "{table}" '
            f'WHERE "{country_col}" IS NOT NULL AND "{country_col}" != \'\' '
            f'GROUP BY "{country_col}" ORDER BY cnt DESC'
        ).fetchall()

        entities = []
        for r in rows:
            entity_name = r["country"]
            entry: dict[str, Any] = {
                "country": entity_name,
                "count": r["cnt"],
            }

            # Bands worked for this entity.
            if band_col:
                band_rows = conn.execute(
                    f'SELECT DISTINCT "{band_col}" AS b FROM "{table}" '
                    f'WHERE "{country_col}" = ? AND "{band_col}" IS NOT NULL',
                    (entity_name,),
                ).fetchall()
                entry["bands_worked"] = [br["b"] for br in band_rows]

            # Modes worked for this entity.
            if mode_col:
                mode_rows = conn.execute(
                    f'SELECT DISTINCT "{mode_col}" AS m FROM "{table}" '
                    f'WHERE "{country_col}" = ? AND "{mode_col}" IS NOT NULL',
                    (entity_name,),
                ).fetchall()
                entry["modes_worked"] = [mr["m"] for mr in mode_rows]

            # Confirmation status.
            confirmed_lotw = False
            confirmed_qsl = False
            if lotw_rcvd_col:
                lr = conn.execute(
                    f'SELECT count(*) AS cnt FROM "{table}" '
                    f'WHERE "{country_col}" = ? '
                    f'AND "{lotw_rcvd_col}" IS NOT NULL '
                    f'AND "{lotw_rcvd_col}" NOT IN (\'\', \'N\', \'0\')',
                    (entity_name,),
                ).fetchone()
                confirmed_lotw = (lr["cnt"] > 0) if lr else False

            if qsl_rcvd_col:
                qr = conn.execute(
                    f'SELECT count(*) AS cnt FROM "{table}" '
                    f'WHERE "{country_col}" = ? '
                    f'AND "{qsl_rcvd_col}" IS NOT NULL '
                    f'AND "{qsl_rcvd_col}" NOT IN (\'\', \'N\', \'0\')',
                    (entity_name,),
                ).fetchone()
                confirmed_qsl = (qr["cnt"] > 0) if qr else False

            entry["confirmed_lotw"] = confirmed_lotw
            entry["confirmed_qsl"] = confirmed_qsl

            entities.append(entry)

        return entities


@router.get("/search")
async def search_qsos(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Full-text search across call, name, country, and comment fields."""
    with _get_connection() as conn:
        schema = _introspect_schema(conn)

        # Build search across available text columns.
        search_cols = ["call", "name", "country", "comment", "grid"]
        or_clauses: list[str] = []
        params: list[Any] = []

        for lc in search_cols:
            actual = _col(schema, lc)
            if actual:
                or_clauses.append(f'"{actual}" LIKE ?')
                params.append(f"%{q}%")

        if not or_clauses:
            return []

        select_cols = [
            "call", "band", "mode", "freq", "qso_date", "time_on",
            "grid", "country", "comment", "name",
        ]
        select = _select_clause(schema, select_cols)
        if not select:
            select = "*"

        where = f"WHERE ({' OR '.join(or_clauses)})"
        order_col = _col(schema, "qso_date") or schema.all_columns[0]

        sql = (
            f'SELECT {select} FROM "{schema.table_name}" '
            f'{where} ORDER BY "{order_col}" DESC LIMIT ?'
        )
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [_row_to_dict(r) for r in rows]


@router.get("/contests")
async def get_contests():
    """Contest participation summary."""
    with _get_connection() as conn:
        schema = _introspect_schema(conn)

        contest_col = _col(schema, "contest")
        if not contest_col:
            return []

        date_col = _col(schema, "qso_date")

        if date_col:
            rows = conn.execute(
                f'SELECT "{contest_col}" AS contest, count(*) AS cnt, '
                f'MIN("{date_col}") AS first_qso, MAX("{date_col}") AS last_qso '
                f'FROM "{schema.table_name}" '
                f'WHERE "{contest_col}" IS NOT NULL AND "{contest_col}" != \'\' '
                f'GROUP BY "{contest_col}" ORDER BY cnt DESC'
            ).fetchall()
        else:
            rows = conn.execute(
                f'SELECT "{contest_col}" AS contest, count(*) AS cnt '
                f'FROM "{schema.table_name}" '
                f'WHERE "{contest_col}" IS NOT NULL AND "{contest_col}" != \'\' '
                f'GROUP BY "{contest_col}" ORDER BY cnt DESC'
            ).fetchall()

        return [_row_to_dict(r) for r in rows]


@router.get("/recent")
async def get_recent(limit: int = Query(default=20, ge=1, le=100)):
    """Most recent QSOs (fast path)."""
    with _get_connection() as conn:
        schema = _introspect_schema(conn)

        select_cols = [
            "call", "band", "mode", "freq", "qso_date", "time_on",
            "rst_sent", "rst_rcvd", "grid", "country", "comment",
            "name", "contest",
        ]
        select = _select_clause(schema, select_cols)
        if not select:
            select = "*"

        order_col = _col(schema, "qso_date") or schema.all_columns[0]
        sql = (
            f'SELECT {select} FROM "{schema.table_name}" '
            f'ORDER BY "{order_col}" DESC LIMIT ?'
        )

        rows = conn.execute(sql, (limit,)).fetchall()
        return [_row_to_dict(r) for r in rows]


@router.get("/daily-summary")
async def get_daily_summary(
    date: str | None = Query(
        default=None, description="YYYY-MM-DD, defaults to yesterday",
    ),
    days: int = Query(default=1, ge=1, le=30),
):
    """Daily QSO summary for knowledge base sync."""
    from datetime import datetime, timedelta, timezone

    if date:
        start = date
    else:
        start = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    # Calculate end date.
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = start_dt + timedelta(days=days)
    end = end_dt.strftime("%Y-%m-%d")

    with _get_connection() as conn:
        schema = _introspect_schema(conn)
        table = schema.table_name

        date_col = _col(schema, "qso_date")
        if not date_col:
            return {"date": start, "days": days, "qso_count": 0}

        call_col = _col(schema, "call")
        band_col = _col(schema, "band")
        mode_col = _col(schema, "mode")
        country_col = _col(schema, "country")

        # Total QSO count for period.
        row = conn.execute(
            f'SELECT count(*) AS cnt FROM "{table}" '
            f'WHERE "{date_col}" >= ? AND "{date_col}" < ?',
            (start, end),
        ).fetchone()
        qso_count = row["cnt"] if row else 0

        result: dict[str, Any] = {
            "date": start,
            "days": days,
            "qso_count": qso_count,
        }

        if qso_count == 0:
            return result

        # Unique calls.
        if call_col:
            row = conn.execute(
                f'SELECT count(DISTINCT "{call_col}") AS cnt FROM "{table}" '
                f'WHERE "{date_col}" >= ? AND "{date_col}" < ?',
                (start, end),
            ).fetchone()
            result["unique_calls"] = row["cnt"] if row else 0

        # Unique countries.
        if country_col:
            row = conn.execute(
                f'SELECT count(DISTINCT "{country_col}") AS cnt FROM "{table}" '
                f'WHERE "{date_col}" >= ? AND "{date_col}" < ? '
                f'AND "{country_col}" IS NOT NULL AND "{country_col}" != \'\'',
                (start, end),
            ).fetchone()
            result["unique_countries"] = row["cnt"] if row else 0

        # Bands used.
        if band_col:
            rows = conn.execute(
                f'SELECT "{band_col}" AS band, count(*) AS cnt FROM "{table}" '
                f'WHERE "{date_col}" >= ? AND "{date_col}" < ? '
                f'AND "{band_col}" IS NOT NULL '
                f'GROUP BY "{band_col}" ORDER BY cnt DESC',
                (start, end),
            ).fetchall()
            result["bands"] = {r["band"]: r["cnt"] for r in rows}

        # Modes used.
        if mode_col:
            rows = conn.execute(
                f'SELECT "{mode_col}" AS mode, count(*) AS cnt FROM "{table}" '
                f'WHERE "{date_col}" >= ? AND "{date_col}" < ? '
                f'AND "{mode_col}" IS NOT NULL '
                f'GROUP BY "{mode_col}" ORDER BY cnt DESC',
                (start, end),
            ).fetchall()
            result["modes"] = {r["mode"]: r["cnt"] for r in rows}

        # Notable QSOs (first 10 unique countries for that day).
        if country_col and call_col:
            select_parts = [f'"{call_col}" AS call', f'"{country_col}" AS country']
            if band_col:
                select_parts.append(f'"{band_col}" AS band')
            if mode_col:
                select_parts.append(f'"{mode_col}" AS mode')

            select_str = ", ".join(select_parts)
            rows = conn.execute(
                f'SELECT {select_str} FROM "{table}" '
                f'WHERE "{date_col}" >= ? AND "{date_col}" < ? '
                f'AND "{country_col}" IS NOT NULL AND "{country_col}" != \'\' '
                f'GROUP BY "{country_col}" '
                f'ORDER BY "{date_col}" DESC LIMIT 10',
                (start, end),
            ).fetchall()
            result["notable_qsos"] = [_row_to_dict(r) for r in rows]

        return result
