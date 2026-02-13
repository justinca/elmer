"""Home Assistant integration — fetch entity states and sync to RAG knowledge base."""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import settings
from . import db

logger = logging.getLogger("elmer.homeassistant")

FETCH_TIMEOUT = 15.0
EMBED_TIMEOUT = 60.0
CACHE_TTL = 60.0  # 1 minute in-memory state cache


class HAService:
    """Home Assistant REST API client with RAG knowledge base sync."""

    def __init__(self) -> None:
        self._states_cache: list[dict[str, Any]] = []
        self._cache_time: float = 0.0

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.HA_TOKEN}",
            "Content-Type": "application/json",
        }

    @property
    def configured(self) -> bool:
        return bool(settings.HA_URL and settings.HA_TOKEN)

    # ------------------------------------------------------------------
    # API methods
    # ------------------------------------------------------------------

    async def get_states(self) -> list[dict[str, Any]]:
        """Fetch all entity states, with 60s in-memory cache."""
        now = time.monotonic()
        if self._states_cache and (now - self._cache_time) < CACHE_TTL:
            return self._states_cache

        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.HA_URL}/api/states", headers=self._headers
            )
            resp.raise_for_status()
            self._states_cache = resp.json()
            self._cache_time = now
            return self._states_cache

    async def get_state(self, entity_id: str) -> dict[str, Any] | None:
        """Fetch a single entity state."""
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.HA_URL}/api/states/{entity_id}",
                headers=self._headers,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def get_history(
        self, entity_id: str, hours: int = 24
    ) -> list[Any]:
        """Fetch state history for an entity."""
        from datetime import timedelta

        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        ts = start.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.HA_URL}/api/history/period/{ts}",
                headers=self._headers,
                params={"filter_entity_id": entity_id, "minimal_response": ""},
            )
            resp.raise_for_status()
            data = resp.json()
            return data[0] if data else []

    async def get_summary(self) -> str:
        """Generate a human-readable home status summary in Markdown."""
        states = await self.get_states()
        return _build_summary(states)

    # ------------------------------------------------------------------
    # RAG knowledge base sync
    # ------------------------------------------------------------------

    async def sync_to_knowledge_base(self) -> dict[str, Any]:
        """Generate markdown snapshots of HA data and upsert into documents table.

        Produces 4 documents with source='homeassistant':
          - ha/home-status.md  (people, weather, climate)
          - ha/security.md     (doors, windows, cameras)
          - ha/devices.md      (printer, garden, meshtastic)
          - ha/automations.md  (active automations)
        """
        pool = db.get_pool()
        if pool is None:
            return {"status": "error", "reason": "database not connected"}

        if not self.configured:
            return {"status": "skipped", "reason": "HA not configured"}

        start = time.monotonic()
        try:
            states = await self.get_states()
        except Exception as exc:
            logger.error("Failed to fetch HA states: %s", exc)
            return {"status": "error", "reason": str(exc)}

        by_domain = _group_by_domain(states)

        docs = {
            "ha/home-status.md": _doc_home_status(by_domain),
            "ha/security.md": _doc_security(by_domain),
            "ha/devices.md": _doc_devices(by_domain),
            "ha/automations.md": _doc_automations(by_domain),
        }

        stored = 0
        for source_path, content in docs.items():
            try:
                embedding = await _get_embedding(content)
                vec_str = "[" + ",".join(str(f) for f in embedding) + "]"

                title = source_path.replace("ha/", "").replace(".md", "").replace("-", " ").title()

                await db.execute(
                    """INSERT INTO elmer.documents
                        (source, source_path, title, content, content_type,
                         embedding, updated_at)
                    VALUES ($1, $2, $3, $4, 'text/markdown', $5::vector, now())
                    ON CONFLICT (source, source_path)
                        WHERE source IS NOT NULL AND source_path IS NOT NULL
                    DO UPDATE SET title=EXCLUDED.title, content=EXCLUDED.content,
                        embedding=EXCLUDED.embedding, updated_at=now()""",
                    "homeassistant",
                    source_path,
                    title,
                    content,
                    vec_str,
                )
                stored += 1
            except Exception:
                logger.warning("Failed to store HA doc %s", source_path, exc_info=True)

        duration = time.monotonic() - start
        logger.info("HA sync: %d/%d docs stored in %.2fs", stored, len(docs), duration)

        return {
            "status": "ok",
            "docs_stored": stored,
            "docs_total": len(docs),
            "entities_fetched": len(states),
            "duration_seconds": round(duration, 3),
        }


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_service: HAService | None = None


def get_service() -> HAService:
    global _service
    if _service is None:
        _service = HAService()
    return _service


# ------------------------------------------------------------------
# Document builders
# ------------------------------------------------------------------


def _group_by_domain(states: list[dict]) -> dict[str, list[dict]]:
    """Group entities by their domain (sensor, climate, binary_sensor, etc.)."""
    groups: dict[str, list[dict]] = {}
    for s in states:
        domain = s.get("entity_id", "").split(".")[0]
        groups.setdefault(domain, []).append(s)
    return groups


def _friendly(entity: dict) -> str:
    """Get friendly name for an entity."""
    return entity.get("attributes", {}).get("friendly_name", entity.get("entity_id", "?"))


def _doc_home_status(by_domain: dict[str, list[dict]]) -> str:
    """Build home status document: people, weather, climate zones."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Home Status\n\nLast updated: {now}\n"]

    # People
    people = by_domain.get("person", [])
    if people:
        lines.append("## People\n")
        for p in people:
            lines.append(f"- **{_friendly(p)}**: {p.get('state', 'unknown')}")
        lines.append("")

    # Weather
    weather = by_domain.get("weather", [])
    if weather:
        w = weather[0]
        attrs = w.get("attributes", {})
        lines.append("## Weather\n")
        lines.append(f"- Condition: {w.get('state', '?')}")
        if "temperature" in attrs:
            lines.append(f"- Temperature: {attrs['temperature']}°{attrs.get('temperature_unit', 'F')}")
        if "humidity" in attrs:
            lines.append(f"- Humidity: {attrs['humidity']}%")
        if "wind_speed" in attrs:
            lines.append(f"- Wind: {attrs['wind_speed']} {attrs.get('wind_speed_unit', 'mph')}")
        if "pressure" in attrs:
            lines.append(f"- Pressure: {attrs['pressure']} {attrs.get('pressure_unit', 'inHg')}")
        lines.append("")

    # Outdoor sensors
    sensors = by_domain.get("sensor", [])
    outdoor_keywords = ["outside_temp", "humidity", "wind_speed", "todays_rain", "barometer"]
    outdoor = [s for s in sensors if any(kw in s.get("entity_id", "") for kw in outdoor_keywords)]
    if outdoor:
        lines.append("## Outdoor Sensors\n")
        for s in outdoor:
            unit = s.get("attributes", {}).get("unit_of_measurement", "")
            lines.append(f"- {_friendly(s)}: {s.get('state', '?')} {unit}")
        lines.append("")

    # Climate zones
    climate = by_domain.get("climate", [])
    if climate:
        lines.append("## Climate Zones\n")
        for c in climate:
            attrs = c.get("attributes", {})
            current = attrs.get("current_temperature", "?")
            target = attrs.get("temperature", "?")
            mode = c.get("state", "?")
            lines.append(f"- **{_friendly(c)}**: {current}°F (target {target}°F, mode: {mode})")
        lines.append("")

    return "\n".join(lines)


def _doc_security(by_domain: dict[str, list[dict]]) -> str:
    """Build security document: doors, windows, locks, cameras."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Security Status\n\nLast updated: {now}\n"]

    binary = by_domain.get("binary_sensor", [])
    doors = [s for s in binary if any(kw in s.get("entity_id", "") for kw in ["door", "window", "lock", "garage"])]
    if doors:
        lines.append("## Doors & Windows\n")
        for d in doors:
            state = d.get("state", "?")
            icon = "OPEN" if state == "on" else "closed"
            lines.append(f"- {_friendly(d)}: {icon}")
        lines.append("")

    # Lock entities
    locks = by_domain.get("lock", [])
    if locks:
        lines.append("## Locks\n")
        for l in locks:
            lines.append(f"- {_friendly(l)}: {l.get('state', '?')}")
        lines.append("")

    # Camera entities
    cameras = by_domain.get("camera", [])
    if cameras:
        lines.append("## Cameras\n")
        for c in cameras:
            lines.append(f"- {_friendly(c)}: {c.get('state', '?')}")
        lines.append("")

    return "\n".join(lines)


def _doc_devices(by_domain: dict[str, list[dict]]) -> str:
    """Build devices document: 3D printer, garden, meshtastic, misc."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Device Status\n\nLast updated: {now}\n"]

    sensors = by_domain.get("sensor", [])
    binary = by_domain.get("binary_sensor", [])
    all_entities = sensors + binary

    # 3D Printer / OctoPrint
    printer = [s for s in all_entities if "octoprint" in s.get("entity_id", "").lower()]
    if printer:
        lines.append("## 3D Printer\n")
        for p in printer:
            unit = p.get("attributes", {}).get("unit_of_measurement", "")
            lines.append(f"- {_friendly(p)}: {p.get('state', '?')} {unit}")
        lines.append("")

    # Garden
    garden = [s for s in all_entities if any(kw in s.get("entity_id", "").lower() for kw in ["garden", "soil", "hose", "water"])]
    if garden:
        lines.append("## Garden\n")
        for g in garden:
            unit = g.get("attributes", {}).get("unit_of_measurement", "")
            lines.append(f"- {_friendly(g)}: {g.get('state', '?')} {unit}")
        lines.append("")

    # Meshtastic
    trackers = by_domain.get("device_tracker", [])
    mesh = [t for t in trackers if "meshtastic" in _friendly(t).lower() or "mesh" in t.get("entity_id", "").lower()]
    if mesh:
        lines.append("## Meshtastic Nodes\n")
        for m in mesh:
            attrs = m.get("attributes", {})
            lines.append(f"- {_friendly(m)}: {m.get('state', '?')}")
            if "battery_level" in attrs:
                lines.append(f"  Battery: {attrs['battery_level']}%")
        lines.append("")

    # Switches and plugs
    switches = by_domain.get("switch", [])
    if switches:
        lines.append("## Switches\n")
        for s in switches:
            lines.append(f"- {_friendly(s)}: {s.get('state', '?')}")
        lines.append("")

    return "\n".join(lines)


def _doc_automations(by_domain: dict[str, list[dict]]) -> str:
    """Build automations document."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Automations\n\nLast updated: {now}\n"]

    automations = by_domain.get("automation", [])
    if automations:
        lines.append("## Active Automations\n")
        for a in automations:
            state = a.get("state", "?")
            last_triggered = a.get("attributes", {}).get("last_triggered", "never")
            lines.append(f"- **{_friendly(a)}**: {state} (last triggered: {last_triggered})")
        lines.append("")

    # Scenes
    scenes = by_domain.get("scene", [])
    if scenes:
        lines.append("## Scenes\n")
        for s in scenes:
            lines.append(f"- {_friendly(s)}")
        lines.append("")

    # Scripts
    scripts = by_domain.get("script", [])
    if scripts:
        lines.append("## Scripts\n")
        for s in scripts:
            lines.append(f"- {_friendly(s)}: {s.get('state', '?')}")
        lines.append("")

    return "\n".join(lines)


def _build_summary(states: list[dict]) -> str:
    """Build a concise human-readable summary of the entire home."""
    by_domain = _group_by_domain(states)
    parts = [
        _doc_home_status(by_domain),
        _doc_security(by_domain),
        _doc_devices(by_domain),
    ]
    return "\n---\n\n".join(parts)


# ------------------------------------------------------------------
# Embedding helper (reuse pattern from rag_chat)
# ------------------------------------------------------------------


async def _get_embedding(text: str) -> list[float]:
    """Generate embedding via worker, falling back to Ollama direct."""
    worker_url = f"{settings.worker_base_url}/llm/embed"
    ollama_url = f"{settings.ollama_base_url}/api/embed"
    payload = {"model": "nomic-embed-text", "input": text}

    async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
        try:
            resp = await client.post(worker_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings") or []
            if embeddings:
                return embeddings[0]
            embedding = data.get("embedding") or []
            if embedding:
                return embedding
        except (httpx.RequestError, RuntimeError) as exc:
            logger.warning("Worker embed failed (%s), trying Ollama direct", exc)

    async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
        resp = await client.post(ollama_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings") or []
        if embeddings:
            return embeddings[0]
        embedding = data.get("embedding") or []
        if embedding:
            return embedding

    raise RuntimeError("No embeddings returned from worker or Ollama")
