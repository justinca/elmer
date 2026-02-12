"""Knowledge scheduler — Obsidian sync + Elmer docs auto-ingestion.

Entry point for the knowledge Docker container:
    python -m src.scheduler
"""

import asyncio
import logging
from pathlib import Path

from .config import settings
from .ingest import DocumentIngestor
from .obsidian_sync import ObsidianSync

logger = logging.getLogger("elmer.knowledge.scheduler")


async def _ingest_elmer_docs(ingestor: DocumentIngestor) -> None:
    """Ingest all markdown files from the Elmer docs directory."""
    docs_path = settings.ELMER_DOCS_PATH
    if not Path(docs_path).is_dir():
        logger.warning("Elmer docs path does not exist: %s", docs_path)
        return

    result = await ingestor.ingest_directory(
        docs_path,
        source="elmer-docs",
        recursive=True,
        patterns=["*.md"],
    )
    logger.info(
        "Elmer docs ingestion: %d ingested, %d skipped, %d errors",
        result.ingested, result.skipped, len(result.errors),
    )


async def run_scheduler() -> None:
    """Run the sync scheduler loop."""
    sync = ObsidianSync()
    await sync.connect_db()

    ingestor = DocumentIngestor()
    await ingestor.connect_db()

    interval = settings.OBSIDIAN_SYNC_INTERVAL
    logger.info(
        "Knowledge scheduler started (interval=%ds, worker=%s)",
        interval, settings.worker_base_url,
    )

    # Run a full Obsidian sync on first start.
    try:
        result = await sync.full_sync()
        await sync.publish_mqtt(result)
        logger.info(
            "Initial full sync: +%d ~%d -%d =%d",
            result.added, result.updated, result.deleted, result.unchanged,
        )
    except Exception:
        logger.exception("Initial full sync failed — will retry as incremental")

    # Ingest Elmer's own docs on startup.
    try:
        await _ingest_elmer_docs(ingestor)
    except Exception:
        logger.exception("Initial Elmer docs ingestion failed — will retry next interval")

    # Periodic loop: Obsidian sync + docs re-ingestion.
    try:
        while True:
            await asyncio.sleep(interval)

            # Obsidian incremental sync.
            try:
                result = await sync.incremental_sync()
                await sync.publish_mqtt(result)
            except Exception:
                logger.exception("Incremental sync failed — will retry next interval")

            # Re-ingest Elmer docs (catches new/changed files).
            try:
                await _ingest_elmer_docs(ingestor)
            except Exception:
                logger.exception("Docs re-ingestion failed — will retry next interval")
    finally:
        await sync.close_db()
        await ingestor.close_db()


async def main() -> None:
    """Entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Elmer Knowledge Scheduler starting...")
    try:
        await run_scheduler()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    asyncio.run(main())
