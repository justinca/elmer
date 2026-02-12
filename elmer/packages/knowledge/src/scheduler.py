"""Obsidian sync scheduler — periodic incremental sync with MQTT notification.

Entry point for the knowledge Docker container:
    python -m src.scheduler
"""

import asyncio
import logging

from .config import settings
from .obsidian_sync import ObsidianSync

logger = logging.getLogger("elmer.knowledge.scheduler")


async def run_scheduler() -> None:
    """Run the sync scheduler loop."""
    sync = ObsidianSync()
    await sync.connect_db()

    interval = settings.OBSIDIAN_SYNC_INTERVAL
    logger.info(
        "Obsidian sync scheduler started (interval=%ds, worker=%s)",
        interval, settings.worker_base_url,
    )

    # Run a full sync on first start.
    try:
        result = await sync.full_sync()
        await sync.publish_mqtt(result)
        logger.info(
            "Initial full sync: +%d ~%d -%d =%d",
            result.added, result.updated, result.deleted, result.unchanged,
        )
    except Exception:
        logger.exception("Initial full sync failed — will retry as incremental")

    # Then incremental syncs on interval.
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                result = await sync.incremental_sync()
                await sync.publish_mqtt(result)
            except Exception:
                logger.exception("Incremental sync failed — will retry next interval")
    finally:
        await sync.close_db()


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
