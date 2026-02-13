"""Needs list — DXCC entities, bands, and modes still needed for W0ABE.

Manages a list of "wanted" DX and checks incoming spots against it.
Pre-populates with commonly sought rare DXCC entities.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from ..services import db

logger = logging.getLogger("elmer.needs_list")


@dataclass
class Need:
    id: int
    entity: str
    band: str | None
    mode: str | None
    priority: int
    notes: str | None
    needed: bool


@dataclass
class NeedMatch:
    matched: bool = False
    needs: list[Need] | None = None
    urgency: str = ""  # "rare", "notable", "routine"


# Starter needs list — commonly sought rare/semi-rare DXCC entities.
_STARTER_NEEDS: list[dict[str, Any]] = [
    {"entity": "Bouvet I.", "priority": 1, "notes": "Extremely rare, #2 most wanted"},
    {"entity": "North Korea", "priority": 1, "notes": "Never activated"},
    {"entity": "Scarborough Reef", "priority": 1, "notes": "Very rare"},
    {"entity": "Heard I.", "priority": 2, "notes": "Rare sub-Antarctic"},
    {"entity": "Crozet I.", "priority": 2, "notes": "Rare sub-Antarctic"},
    {"entity": "Amsterdam & St. Paul", "priority": 2, "notes": "Rare sub-Antarctic"},
    {"entity": "Kerguelen", "priority": 2, "notes": "Rare sub-Antarctic"},
    {"entity": "Navassa I.", "priority": 2, "notes": "Very rare Caribbean"},
    {"entity": "Pratas I.", "priority": 2, "notes": "Very rare Asia"},
    {"entity": "Andaman & Nicobar", "priority": 3, "notes": "Semi-rare Asia"},
    {"entity": "Lakshadweep Is.", "priority": 3, "notes": "Semi-rare Asia"},
    {"entity": "Mount Athos", "priority": 3, "notes": "Rare EU autonomous"},
    {"entity": "South Sandwich", "priority": 3, "notes": "Rare sub-Antarctic"},
    {"entity": "South Georgia", "priority": 3, "notes": "Rare sub-Antarctic"},
    {"entity": "Annobon I.", "priority": 3, "notes": "Rare Africa"},
    {"entity": "Baker & Howland", "priority": 3, "notes": "Rare Pacific"},
    {"entity": "Kure I.", "priority": 3, "notes": "Rare Pacific"},
    {"entity": "Bhutan", "priority": 4, "notes": "Semi-rare Asia"},
    {"entity": "Yemen", "priority": 4, "notes": "Semi-rare Middle East"},
    {"entity": "Eritrea", "priority": 4, "notes": "Semi-rare Africa"},
    {"entity": "Somalia", "priority": 4, "notes": "Semi-rare Africa"},
    {"entity": "Comoros", "priority": 4, "notes": "Semi-rare Africa"},
    {"entity": "Seychelles", "priority": 5, "notes": "Moderate Africa"},
    {"entity": "Reunion", "priority": 5, "notes": "Moderate Africa"},
    {"entity": "Chatham Is.", "priority": 5, "notes": "Moderate Oceania"},
    {"entity": "Norfolk I.", "priority": 5, "notes": "Moderate Oceania"},
]


class NeedsList:
    """Manage the operator's DXCC needs list."""

    async def add_need(
        self,
        entity: str,
        band: str | None = None,
        mode: str | None = None,
        priority: int = 5,
        notes: str | None = None,
    ) -> dict:
        """Add an entry to the needs list."""
        row = await db.fetch_one(
            """
            INSERT INTO elmer.needs_list (entity, band, mode, priority, notes, needed)
            VALUES ($1, $2, $3, $4, $5, true)
            RETURNING id, entity, band, mode, priority, notes, needed
            """,
            entity, band, mode, priority, notes,
        )
        return dict(row) if row else {}

    async def remove_need(self, need_id: int) -> bool:
        """Remove a need by ID (mark as not needed)."""
        result = await db.execute(
            "UPDATE elmer.needs_list SET needed = false, confirmed_at = now() WHERE id = $1",
            need_id,
        )
        return not result.endswith("0")

    async def delete_need(self, need_id: int) -> bool:
        """Hard-delete a need by ID."""
        result = await db.execute(
            "DELETE FROM elmer.needs_list WHERE id = $1", need_id,
        )
        return not result.endswith("0")

    async def get_needs(self, entity: str | None = None) -> list[Need]:
        """Get current needs list, optionally filtered by entity."""
        if entity:
            rows = await db.fetch_all(
                """SELECT id, entity, band, mode, priority, notes, needed
                   FROM elmer.needs_list
                   WHERE needed = true AND entity ILIKE $1
                   ORDER BY priority, entity""",
                f"%{entity}%",
            )
        else:
            rows = await db.fetch_all(
                """SELECT id, entity, band, mode, priority, notes, needed
                   FROM elmer.needs_list
                   WHERE needed = true
                   ORDER BY priority, entity""",
            )
        return [
            Need(
                id=r["id"],
                entity=r["entity"],
                band=r.get("band"),
                mode=r.get("mode"),
                priority=r["priority"],
                notes=r.get("notes"),
                needed=r["needed"],
            )
            for r in rows
        ]

    async def check_spot(self, dx_entity: str, band: str, mode: str) -> NeedMatch:
        """Check if a spot matches something on the needs list."""
        if not dx_entity:
            return NeedMatch()

        # Query for matching needs.
        rows = await db.fetch_all(
            """
            SELECT id, entity, band, mode, priority, notes, needed
            FROM elmer.needs_list
            WHERE needed = true
              AND entity ILIKE $1
              AND (band IS NULL OR band = $2)
              AND (mode IS NULL OR mode = $3)
            ORDER BY priority
            """,
            f"%{dx_entity}%", band, mode,
        )

        if not rows:
            # Also check if the entity itself matches (without band/mode filter).
            entity_rows = await db.fetch_all(
                """
                SELECT id, entity, band, mode, priority, notes, needed
                FROM elmer.needs_list
                WHERE needed = true AND entity ILIKE $1
                ORDER BY priority
                """,
                f"%{dx_entity}%",
            )
            if entity_rows:
                needs = [
                    Need(
                        id=r["id"], entity=r["entity"],
                        band=r.get("band"), mode=r.get("mode"),
                        priority=r["priority"], notes=r.get("notes"),
                        needed=r["needed"],
                    )
                    for r in entity_rows
                ]
                # Entity matches but maybe not exact band/mode.
                urgency = "rare" if needs[0].priority <= 2 else "notable"
                return NeedMatch(matched=True, needs=needs, urgency=urgency)
            return NeedMatch()

        needs = [
            Need(
                id=r["id"], entity=r["entity"],
                band=r.get("band"), mode=r.get("mode"),
                priority=r["priority"], notes=r.get("notes"),
                needed=r["needed"],
            )
            for r in rows
        ]

        # Determine urgency based on priority.
        best_priority = min(n.priority for n in needs)
        if best_priority <= 2:
            urgency = "rare"
        elif best_priority <= 4:
            urgency = "notable"
        else:
            urgency = "routine"

        return NeedMatch(matched=True, needs=needs, urgency=urgency)

    async def mark_worked(
        self,
        entity: str,
        band: str | None = None,
        mode: str | None = None,
    ) -> list[int]:
        """Mark matching needs as confirmed worked. Returns list of marked need IDs."""
        if band and mode:
            rows = await db.fetch_all(
                """UPDATE elmer.needs_list
                   SET needed = false, confirmed_at = now()
                   WHERE needed = true
                     AND entity ILIKE $1
                     AND (band IS NULL OR band = $2)
                     AND (mode IS NULL OR mode = $3)
                   RETURNING id""",
                f"%{entity}%", band, mode,
            )
        elif band:
            rows = await db.fetch_all(
                """UPDATE elmer.needs_list
                   SET needed = false, confirmed_at = now()
                   WHERE needed = true
                     AND entity ILIKE $1
                     AND (band IS NULL OR band = $2)
                   RETURNING id""",
                f"%{entity}%", band,
            )
        elif mode:
            rows = await db.fetch_all(
                """UPDATE elmer.needs_list
                   SET needed = false, confirmed_at = now()
                   WHERE needed = true
                     AND entity ILIKE $1
                     AND (mode IS NULL OR mode = $2)
                   RETURNING id""",
                f"%{entity}%", mode,
            )
        else:
            rows = await db.fetch_all(
                """UPDATE elmer.needs_list
                   SET needed = false, confirmed_at = now()
                   WHERE needed = true AND entity ILIKE $1
                   RETURNING id""",
                f"%{entity}%",
            )

        marked = [r["id"] for r in rows]
        if marked:
            logger.info("Marked %d needs as worked for entity=%s", len(marked), entity)
        return marked

    async def populate_starter(self) -> int:
        """Populate the needs list with starter entries if empty."""
        existing = await db.fetch_one(
            "SELECT count(*) AS cnt FROM elmer.needs_list WHERE needed = true"
        )
        if existing and existing["cnt"] > 0:
            return 0

        count = 0
        for entry in _STARTER_NEEDS:
            try:
                await db.execute(
                    """
                    INSERT INTO elmer.needs_list (entity, priority, notes, needed)
                    VALUES ($1, $2, $3, true)
                    ON CONFLICT DO NOTHING
                    """,
                    entry["entity"],
                    entry["priority"],
                    entry.get("notes", ""),
                )
                count += 1
            except Exception:
                logger.debug("Failed to insert starter need: %s", entry["entity"])

        if count:
            logger.info("Populated needs list with %d starter entries", count)
        return count


# Module-level singleton.
_needs: NeedsList | None = None


def get_needs_list() -> NeedsList:
    global _needs
    if _needs is None:
        _needs = NeedsList()
    return _needs
