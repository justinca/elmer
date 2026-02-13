"""Schedule trigger manager — cron and interval triggers via APScheduler."""

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..models import AgentDefinition

logger = logging.getLogger("elmer.triggers.schedule")

EnqueueCallback = Callable[[str, str, dict, dict], Awaitable[None]]


class ScheduleTriggerManager:
    """Manages cron and interval scheduled triggers using APScheduler."""

    def __init__(self, enqueue: EnqueueCallback) -> None:
        self._enqueue = enqueue
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        # agent_name -> [job_id, ...]
        self._job_ids: dict[str, list[str]] = {}

    def start(self) -> None:
        """Start the APScheduler event loop."""
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Schedule trigger manager started")

    def register_agent(self, agent: AgentDefinition) -> int:
        """Create scheduled jobs for *agent*. Returns count registered."""
        count = 0
        jobs: list[str] = []

        for i, trigger in enumerate(agent.triggers):
            if trigger.type != "schedule":
                continue

            job_id = f"{agent.name}_schedule_{i}"

            if trigger.cron:
                parts = trigger.cron.strip().split()
                if len(parts) != 5:
                    logger.warning(
                        "Invalid cron '%s' for agent '%s' — expected 5 fields",
                        trigger.cron, agent.name,
                    )
                    continue
                cron_trigger = CronTrigger(
                    minute=parts[0],
                    hour=parts[1],
                    day=parts[2],
                    month=parts[3],
                    day_of_week=parts[4],
                    timezone="UTC",
                )
                self._scheduler.add_job(
                    self._fire,
                    trigger=cron_trigger,
                    id=job_id,
                    args=[agent.name, trigger.cron, None],
                    replace_existing=True,
                    misfire_grace_time=60,
                )
                logger.info(
                    "Scheduled cron '%s' for agent '%s' (job %s)",
                    trigger.cron, agent.name, job_id,
                )
            elif trigger.interval_seconds:
                self._scheduler.add_job(
                    self._fire,
                    trigger=IntervalTrigger(seconds=trigger.interval_seconds),
                    id=job_id,
                    args=[agent.name, None, trigger.interval_seconds],
                    replace_existing=True,
                    misfire_grace_time=60,
                )
                logger.info(
                    "Scheduled interval %ds for agent '%s' (job %s)",
                    trigger.interval_seconds, agent.name, job_id,
                )
            else:
                continue

            jobs.append(job_id)
            count += 1

        self._job_ids[agent.name] = jobs
        return count

    async def _fire(
        self,
        agent_name: str,
        cron: str | None,
        interval_seconds: int | None,
    ) -> None:
        """Called by APScheduler when a job fires."""
        logger.info("Schedule trigger fired: agent=%s cron=%s interval=%s",
                     agent_name, cron, interval_seconds)
        trigger_data: dict[str, Any] = {
            "type": "schedule",
            "cron": cron,
            "interval_seconds": interval_seconds,
            "fired_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._enqueue(agent_name, "schedule", trigger_data, {})

    def unregister_agent(self, agent_name: str) -> None:
        """Remove all scheduled jobs for *agent_name*."""
        for job_id in self._job_ids.pop(agent_name, []):
            try:
                self._scheduler.remove_job(job_id)
                logger.debug("Removed schedule job %s", job_id)
            except Exception:
                pass

    def get_scheduled_jobs(self) -> list[dict[str, Any]]:
        """Return info about all scheduled jobs for the API."""
        jobs = []
        for job in self._scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "job_id": job.id,
                "agent_name": job.args[0] if job.args else "",
                "cron": job.args[1] if job.args and len(job.args) > 1 else None,
                "interval_seconds": job.args[2] if job.args and len(job.args) > 2 else None,
                "next_run_time": next_run.isoformat() if next_run else None,
            })
        return jobs

    def shutdown(self) -> None:
        """Stop the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Schedule trigger manager stopped")
