"""Unified task scheduler for Elmer Core.

Runs periodic background tasks on configurable intervals:
  - Auto-doc regeneration
  - Elmer docs re-ingestion (with embedding)
  - Stale node detection
  - Obsidian sync trigger (via the /knowledge/ingest/directory endpoint)

Each task publishes its result to MQTT: ``elmer/scheduler/{task_name}``.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine

from ..config import settings
from ..services import db
from .mqtt_service import publish as mqtt_publish

logger = logging.getLogger("elmer.scheduler")

# ---------------------------------------------------------------------------
# Task registry
# ---------------------------------------------------------------------------

_INGEST_TIMESTAMPS: dict[str, float] = {}


class ScheduledTask:
    """Wrapper around a periodic async task."""

    def __init__(
        self,
        name: str,
        func: Callable[..., Coroutine],
        interval_seconds: float,
        run_on_startup: bool = False,
    ) -> None:
        self.name = name
        self.func = func
        self.interval_seconds = interval_seconds
        self.run_on_startup = run_on_startup
        self.last_run: datetime | None = None
        self.last_duration: float = 0.0
        self.run_count: int = 0
        self.error_count: int = 0

    async def execute(self) -> dict[str, Any]:
        """Run the task, track timing, publish result to MQTT."""
        start = time.monotonic()
        self.run_count += 1

        try:
            result = await self.func()
            self.last_duration = time.monotonic() - start
            self.last_run = datetime.now(timezone.utc)

            summary = {
                "task": self.name,
                "status": "ok",
                "duration_seconds": round(self.last_duration, 3),
                "run_count": self.run_count,
                "timestamp": self.last_run.isoformat(),
                "result": result if isinstance(result, dict) else str(result),
            }

            logger.info(
                "Task '%s' completed in %.2fs (run #%d)",
                self.name, self.last_duration, self.run_count,
            )
        except Exception as exc:
            self.last_duration = time.monotonic() - start
            self.error_count += 1

            summary = {
                "task": self.name,
                "status": "error",
                "error": str(exc),
                "duration_seconds": round(self.last_duration, 3),
                "run_count": self.run_count,
                "error_count": self.error_count,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            logger.exception("Task '%s' failed (error #%d)", self.name, self.error_count)

        # Publish result to MQTT.
        try:
            await mqtt_publish(
                f"elmer/scheduler/{self.name}",
                json.dumps(summary, default=str),
            )
        except Exception:
            logger.debug("Failed to publish scheduler result for %s", self.name)

        return summary


# ---------------------------------------------------------------------------
# Task implementations
# ---------------------------------------------------------------------------


async def _task_ingest_docs() -> dict[str, Any]:
    """Ingest Elmer's own documentation into the knowledge base.

    Reads markdown files from docs/, chunks and embeds them.
    Tracks file modification times to skip unchanged files.
    """
    from ..routes.knowledge import _get_embedding, _chunk_for_ingest, _detect_content_type

    docs_dir = Path("/app/docs")
    if not docs_dir.is_dir():
        docs_dir = Path.home() / "elmer" / "docs"
    if not docs_dir.is_dir():
        return {"status": "skipped", "reason": "docs directory not found"}

    # Collect files from auto/, manual/, and top-level .md files.
    targets: list[Path] = []

    for subdir in ["auto", "manual"]:
        sub = docs_dir / subdir
        if sub.is_dir():
            targets.extend(sub.rglob("*.md"))

    # Top-level docs.
    for name in ["architecture.md", "setup.md", "mqtt-topics.md"]:
        p = docs_dir / name
        if p.is_file():
            targets.append(p)

    ingested = 0
    skipped = 0
    errors: list[str] = []

    for file_path in sorted(set(targets)):
        try:
            mtime = file_path.stat().st_mtime
            key = str(file_path)

            # Skip if file hasn't changed since last ingest.
            if key in _INGEST_TIMESTAMPS and _INGEST_TIMESTAMPS[key] >= mtime:
                skipped += 1
                continue

            content = file_path.read_text(encoding="utf-8", errors="replace")
            if not content.strip():
                skipped += 1
                continue

            if len(content) > 1_048_576:
                content = content[:1_048_576]

            suffix = file_path.suffix
            content_type = _detect_content_type(suffix)
            chunks = _chunk_for_ingest(content, file_path.name)

            # Determine source based on parent dir.
            rel = str(file_path.relative_to(docs_dir))
            if rel.startswith("auto/"):
                source = "elmer-autodoc"
            elif rel.startswith("manual/"):
                source = "elmer-manual"
            else:
                source = "elmer-docs"

            stored = 0
            for chunk_info in chunks:
                try:
                    embedding = await _get_embedding(chunk_info["text"])
                    vec_str = "[" + ",".join(str(f) for f in embedding) + "]"
                    source_path = f"{rel}#chunk-{chunk_info['index']}"
                    meta = json.dumps({"chunk_index": chunk_info["index"], "file": rel})

                    await db.execute(
                        """INSERT INTO elmer.documents
                            (source, source_path, title, content, content_type,
                             metadata, embedding, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::vector, now())
                        ON CONFLICT (source, source_path)
                            WHERE source IS NOT NULL AND source_path IS NOT NULL
                        DO UPDATE SET title=EXCLUDED.title, content=EXCLUDED.content,
                            content_type=EXCLUDED.content_type, metadata=EXCLUDED.metadata,
                            embedding=EXCLUDED.embedding, updated_at=now()""",
                        source, source_path, chunk_info["title"],
                        chunk_info["text"], content_type, meta, vec_str,
                    )
                    stored += 1
                except Exception:
                    logger.warning("Failed to embed chunk %d of %s", chunk_info["index"], rel)

            if stored > 0:
                _INGEST_TIMESTAMPS[key] = mtime
                ingested += 1
            else:
                skipped += 1

        except Exception as exc:
            errors.append(f"{file_path.name}: {exc}")

    return {"ingested": ingested, "skipped": skipped, "errors": errors}


async def _task_autodoc_regen() -> dict[str, Any]:
    """Regenerate auto-documentation from live system state."""
    from .autodoc import get_documentor

    documentor = get_documentor()
    if documentor is None:
        return {"status": "skipped", "reason": "documentor not initialized"}

    return await documentor.generate_all()


# ---------------------------------------------------------------------------
# Scheduler runner
# ---------------------------------------------------------------------------


class Scheduler:
    """Manages all scheduled tasks in the core process."""

    def __init__(self) -> None:
        self._tasks: list[ScheduledTask] = []
        self._stop = asyncio.Event()
        self._runner_tasks: list[asyncio.Task] = []

    def add_task(self, task: ScheduledTask) -> None:
        self._tasks.append(task)

    async def start(self) -> None:
        """Start all periodic task runners."""
        logger.info("Scheduler starting with %d tasks", len(self._tasks))

        for task in self._tasks:
            runner = asyncio.create_task(self._run_loop(task))
            self._runner_tasks.append(runner)

    async def _run_loop(self, task: ScheduledTask) -> None:
        """Run a single task on its interval."""
        # Run on startup if configured.
        if task.run_on_startup:
            await task.execute()

        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=task.interval_seconds
                )
                return  # stop was set
            except asyncio.TimeoutError:
                pass

            await task.execute()

    async def stop(self) -> None:
        """Signal all tasks to stop and wait for completion."""
        self._stop.set()
        for runner in self._runner_tasks:
            try:
                await asyncio.wait_for(runner, timeout=5.0)
            except asyncio.TimeoutError:
                runner.cancel()
            except asyncio.CancelledError:
                pass
        self._runner_tasks.clear()
        logger.info("Scheduler stopped.")

    def get_status(self) -> list[dict[str, Any]]:
        """Return status of all scheduled tasks."""
        return [
            {
                "name": t.name,
                "interval_seconds": t.interval_seconds,
                "last_run": t.last_run.isoformat() if t.last_run else None,
                "last_duration_seconds": round(t.last_duration, 3),
                "run_count": t.run_count,
                "error_count": t.error_count,
            }
            for t in self._tasks
        ]


# ---------------------------------------------------------------------------
# Factory — called from main.py lifespan
# ---------------------------------------------------------------------------

_scheduler: Scheduler | None = None


def get_scheduler() -> Scheduler | None:
    return _scheduler


def create_scheduler() -> Scheduler:
    """Create the scheduler with all configured tasks."""
    global _scheduler

    scheduler = Scheduler()

    # Auto-doc regeneration (default: every 6 hours).
    scheduler.add_task(ScheduledTask(
        name="autodoc-regen",
        func=_task_autodoc_regen,
        interval_seconds=settings.AUTODOC_INTERVAL_HOURS * 3600,
        run_on_startup=False,  # Already triggered in lifespan.
    ))

    # Elmer docs ingestion (default: every 6 hours, runs on startup).
    scheduler.add_task(ScheduledTask(
        name="ingest-docs",
        func=_task_ingest_docs,
        interval_seconds=settings.AUTODOC_INTERVAL_HOURS * 3600,
        run_on_startup=True,
    ))

    _scheduler = scheduler
    return scheduler
