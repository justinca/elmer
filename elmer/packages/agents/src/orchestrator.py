"""Agent orchestrator — coordinates triggers, queue, and execution.

The orchestrator is the central coordinator for autonomous agent execution.
It manages three trigger managers (MQTT, schedule, event), maintains a
queue of pending executions, and runs a worker pool that processes them
through the :class:`AgentExecutor`.
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .models import AgentDefinition
from .triggers.mqtt_trigger import MQTTTriggerManager
from .triggers.schedule_trigger import ScheduleTriggerManager
from .triggers.event_trigger import EventTriggerManager

# Circuit breaker: auto-disable after this many consecutive failures.
_CIRCUIT_BREAKER_THRESHOLD = 5
# Rate limit: max executions per agent per hour.
_RATE_LIMIT_PER_HOUR = 60
# Metrics publish interval in seconds.
_METRICS_INTERVAL = 60

logger = logging.getLogger("elmer.orchestrator")


class AgentOrchestrator:
    """Coordinates agent triggers, queuing, and execution.

    Parameters
    ----------
    registry : AgentRegistry
        For loading agent definitions from the database.
    executor : AgentExecutor
        For running agents (Ollama tool-calling loop).
    mqtt_client : ElmerMQTTClient
        For subscribing to trigger topics.
    mqtt_publish : callable
        For publishing status events.
    db : module
        Database module with ``fetch_one``, ``execute``, etc.
    num_workers : int
        Number of concurrent worker tasks pulling from the queue.
    """

    def __init__(
        self,
        registry: Any,
        executor: Any,
        mqtt_client: Any,
        mqtt_publish: Any,
        db: Any,
        num_workers: int = 3,
    ) -> None:
        self._registry = registry
        self._executor = executor
        self._mqtt_publish = mqtt_publish
        self._db = db
        self._num_workers = num_workers

        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._agents: dict[str, AgentDefinition] = {}
        self._running_agents: dict[int, str] = {}  # run_id -> agent_name
        self._workers: list[asyncio.Task] = []
        self._metrics_task: asyncio.Task | None = None
        self._running = False

        # Circuit breaker: consecutive failure count per agent.
        self._failure_counts: dict[str, int] = defaultdict(int)
        # Rate limiting: list of execution timestamps per agent (last hour).
        self._rate_window: dict[str, list[float]] = defaultdict(list)
        # Metrics counters.
        self._total_runs = 0
        self._total_failures = 0

        # Create trigger managers.
        self._mqtt_triggers = MQTTTriggerManager(
            mqtt_client, self._enqueue, debounce_default=30.0,
        )
        self._schedule_triggers = ScheduleTriggerManager(self._enqueue)
        self._event_triggers = EventTriggerManager(mqtt_client, self._enqueue)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Load agents, register triggers, start workers."""
        self._running = True

        # Start the schedule manager (APScheduler event loop).
        self._schedule_triggers.start()

        # Subscribe event manager to MQTT.
        await self._event_triggers.start()

        # Load all enabled agents from the database.
        agents = await self._registry.list_all(enabled_only=True)
        for agent in agents:
            await self._register_agent(agent)

        # Start worker pool.
        for i in range(self._num_workers):
            task = asyncio.create_task(self._worker(i), name=f"orch-worker-{i}")
            self._workers.append(task)

        # Start metrics publisher.
        self._metrics_task = asyncio.create_task(
            self._metrics_loop(), name="orch-metrics",
        )

        logger.info(
            "Orchestrator started: %d agents, %d workers, queue capacity %d",
            len(self._agents), self._num_workers, self._queue.maxsize,
        )

        # Publish status.
        await self._publish_status()

    async def stop(self) -> None:
        """Graceful shutdown — finish current work, cancel workers."""
        logger.info("Orchestrator stopping...")
        self._running = False

        # Shut down the schedule manager.
        self._schedule_triggers.shutdown()

        # Cancel metrics task.
        if self._metrics_task:
            self._metrics_task.cancel()
            try:
                await self._metrics_task
            except asyncio.CancelledError:
                pass

        # Cancel workers and wait for them.
        for worker in self._workers:
            worker.cancel()
        results = await asyncio.gather(*self._workers, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                logger.warning("Worker %d exited with error: %s", i, result)
        self._workers.clear()

        # Drain queue.
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        logger.info("Orchestrator stopped")

    async def reload(self) -> dict[str, int]:
        """Re-read all agent definitions and update triggers."""
        logger.info("Reloading all agent definitions...")

        # Unregister all current agents.
        for name in list(self._agents):
            self._unregister_agent(name)
        self._agents.clear()

        # Re-load from DB.
        agents = await self._registry.list_all(enabled_only=True)
        for agent in agents:
            await self._register_agent(agent)

        status = {
            "agents_registered": len(self._agents),
            "agents": list(self._agents.keys()),
        }
        logger.info("Reload complete: %s", status)
        return status

    async def reload_agent(self, name: str) -> None:
        """Reload a single agent's triggers (e.g. after API update)."""
        # Unregister old triggers.
        self._unregister_agent(name)

        # Re-fetch from DB.
        agent = await self._registry.get(name)
        if agent is not None and agent.enabled:
            await self._register_agent(agent)
            logger.info("Reloaded agent '%s'", name)
        else:
            self._agents.pop(name, None)
            logger.info("Agent '%s' unregistered (disabled or deleted)", name)

    # ------------------------------------------------------------------
    # Trigger registration
    # ------------------------------------------------------------------

    async def _register_agent(self, agent: AgentDefinition) -> None:
        """Register all triggers for a single agent."""
        self._agents[agent.name] = agent

        mqtt_count = await self._mqtt_triggers.register_agent(agent)
        schedule_count = self._schedule_triggers.register_agent(agent)
        event_count = self._event_triggers.register_agent(agent)

        total = mqtt_count + schedule_count + event_count
        if total:
            logger.info(
                "Agent '%s': %d mqtt, %d schedule, %d event triggers",
                agent.name, mqtt_count, schedule_count, event_count,
            )

    def _unregister_agent(self, name: str) -> None:
        """Remove all triggers for a single agent."""
        self._mqtt_triggers.unregister_agent(name)
        self._schedule_triggers.unregister_agent(name)
        self._event_triggers.unregister_agent(name)

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    async def _enqueue(
        self,
        agent_name: str,
        trigger_type: str,
        trigger_data: dict[str, Any],
        input_data: dict[str, Any],
    ) -> None:
        """Called by trigger managers to queue an agent execution."""
        agent = self._agents.get(agent_name)
        if agent is None:
            logger.warning("Trigger for unknown agent '%s' — ignoring", agent_name)
            return
        if not agent.enabled:
            logger.debug("Trigger for disabled agent '%s' — ignoring", agent_name)
            return

        # Rate limiting: prune old entries and check limit.
        now = asyncio.get_event_loop().time()
        window = self._rate_window[agent_name]
        window[:] = [t for t in window if now - t < 3600]
        if len(window) >= _RATE_LIMIT_PER_HOUR:
            logger.warning(
                "Rate limit exceeded for '%s' (%d/%d per hour) — dropping trigger",
                agent_name, len(window), _RATE_LIMIT_PER_HOUR,
            )
            return
        window.append(now)

        item = {
            "agent_name": agent_name,
            "trigger_type": trigger_type,
            "trigger_data": trigger_data,
            "input_data": input_data,
        }

        try:
            self._queue.put_nowait(item)
            logger.debug(
                "Enqueued %s trigger for '%s' (queue size: %d)",
                trigger_type, agent_name, self._queue.qsize(),
            )
        except asyncio.QueueFull:
            logger.warning(
                "Execution queue full (%d), dropping %s trigger for '%s'",
                self._queue.maxsize, trigger_type, agent_name,
            )

    # ------------------------------------------------------------------
    # Worker pool
    # ------------------------------------------------------------------

    async def _worker(self, worker_id: int) -> None:
        """Pull items from the queue and execute agents."""
        logger.debug("Worker %d started", worker_id)

        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            agent_name = item["agent_name"]
            agent = self._agents.get(agent_name)
            if agent is None:
                logger.warning("Worker %d: agent '%s' no longer registered", worker_id, agent_name)
                self._queue.task_done()
                continue

            run_id: int | None = None
            try:
                # Create run record in database.
                run_row = await self._db.fetch_one(
                    """
                    INSERT INTO elmer.agent_runs
                        (agent_id, trigger_type, trigger_data, input_data, status, started_at)
                    VALUES ($1, $2, $3::jsonb, $4::jsonb, 'pending', now())
                    RETURNING id
                    """,
                    agent.id,
                    item["trigger_type"],
                    json.dumps(item["trigger_data"], default=str),
                    json.dumps(item["input_data"], default=str),
                )
                run_id = run_row["id"]

                # Track running agent.
                self._running_agents[run_id] = agent_name

                # Publish triggered event.
                await self._mqtt_publish(
                    f"elmer/agents/{agent_name}/triggered",
                    {
                        "agent": agent_name,
                        "run_id": run_id,
                        "trigger_type": item["trigger_type"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

                # Execute the agent.
                result = await self._executor.execute(
                    agent,
                    run_id,
                    trigger_data=item["trigger_data"],
                    input_data=item["input_data"],
                )

                self._total_runs += 1
                failed = "error" in result
                status = "failed" if failed else "completed"

                # Circuit breaker tracking.
                if failed:
                    self._total_failures += 1
                    self._failure_counts[agent_name] += 1
                    if self._failure_counts[agent_name] >= _CIRCUIT_BREAKER_THRESHOLD:
                        await self._circuit_break(agent_name)
                else:
                    self._failure_counts[agent_name] = 0

                # Persist event to elmer.events.
                await self._record_event(
                    agent_name, status, run_id, item["trigger_type"],
                )

                # Publish completed event.
                await self._mqtt_publish(
                    f"elmer/agents/{agent_name}/completed",
                    {
                        "agent": agent_name,
                        "run_id": run_id,
                        "trigger_type": item["trigger_type"],
                        "status": status,
                        "steps": result.get("steps", 0),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

                logger.info(
                    "Worker %d: agent '%s' run %d %s via %s (%d steps)",
                    worker_id, agent_name, run_id, status,
                    item["trigger_type"], result.get("steps", 0),
                )

            except Exception:
                self._total_runs += 1
                self._total_failures += 1
                self._failure_counts[agent_name] = self._failure_counts.get(agent_name, 0) + 1
                if self._failure_counts[agent_name] >= _CIRCUIT_BREAKER_THRESHOLD:
                    await self._circuit_break(agent_name)
                logger.exception(
                    "Worker %d: failed executing agent '%s' (run %s)",
                    worker_id, agent_name, run_id,
                )
            finally:
                if run_id is not None:
                    self._running_agents.pop(run_id, None)
                self._queue.task_done()

        logger.debug("Worker %d stopped", worker_id)

    # ------------------------------------------------------------------
    # Circuit breaker
    # ------------------------------------------------------------------

    async def _circuit_break(self, agent_name: str) -> None:
        """Disable an agent after repeated failures and alert via Telegram."""
        logger.warning(
            "Circuit breaker tripped for '%s' (%d consecutive failures) — disabling",
            agent_name, self._failure_counts[agent_name],
        )
        self._failure_counts[agent_name] = 0

        # Disable in DB.
        try:
            await self._db.execute(
                "UPDATE elmer.agent_definitions SET enabled = false WHERE name = $1",
                agent_name,
            )
        except Exception:
            logger.exception("Failed to disable agent '%s' in DB", agent_name)

        # Update in-memory state.
        agent = self._agents.get(agent_name)
        if agent:
            agent.enabled = False

        # Unregister triggers.
        self._unregister_agent(agent_name)

        # Record event.
        await self._record_event(
            agent_name, "circuit_breaker_tripped", None, "system",
        )

        # Alert via MQTT (Telegram bot can pick this up).
        try:
            await self._mqtt_publish(
                "elmer/alerts/agent",
                {
                    "agent": agent_name,
                    "event": "circuit_breaker_tripped",
                    "message": f"Agent '{agent_name}' auto-disabled after "
                               f"{_CIRCUIT_BREAKER_THRESHOLD} consecutive failures.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            logger.debug("Failed to publish circuit breaker alert", exc_info=True)

    async def _record_event(
        self,
        agent_name: str,
        event_type: str,
        run_id: int | None,
        trigger_type: str,
    ) -> None:
        """Write an agent event to elmer.events."""
        try:
            await self._db.execute(
                """
                INSERT INTO elmer.events (event_type, source, data, created_at)
                VALUES ($1, $2, $3::jsonb, now())
                """,
                f"agent.{event_type}",
                f"agent:{agent_name}",
                json.dumps({
                    "agent_name": agent_name,
                    "run_id": run_id,
                    "trigger_type": trigger_type,
                }, default=str),
            )
        except Exception:
            logger.debug("Failed to record agent event", exc_info=True)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    async def _metrics_loop(self) -> None:
        """Publish orchestrator metrics to MQTT every interval."""
        while self._running:
            try:
                await asyncio.sleep(_METRICS_INTERVAL)
                await self._publish_metrics()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.debug("Metrics publish error", exc_info=True)

    async def _publish_metrics(self) -> None:
        """Publish current metrics snapshot."""
        try:
            await self._mqtt_publish(
                "elmer/orchestrator/metrics",
                {
                    "agents_registered": len(self._agents),
                    "queue_size": self._queue.qsize(),
                    "running": len(self._running_agents),
                    "total_runs": self._total_runs,
                    "total_failures": self._total_failures,
                    "circuit_breakers": {
                        name: count
                        for name, count in self._failure_counts.items()
                        if count > 0
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            logger.debug("Failed to publish metrics", exc_info=True)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return orchestrator status for the API."""
        return {
            "running": self._running,
            "agents_registered": len(self._agents),
            "queue_size": self._queue.qsize(),
            "queue_capacity": self._queue.maxsize,
            "workers": len(self._workers),
            "running_agents": dict(self._running_agents),
            "agents": sorted(self._agents.keys()),
            "total_runs": self._total_runs,
            "total_failures": self._total_failures,
            "failure_counts": dict(self._failure_counts),
        }

    def get_running_agents(self) -> list[str]:
        """Return names of currently executing agents."""
        return list(self._running_agents.values())

    async def _publish_status(self) -> None:
        """Publish orchestrator status to MQTT."""
        try:
            await self._mqtt_publish(
                "elmer/orchestrator/status",
                {
                    "status": "running" if self._running else "stopped",
                    "agents": len(self._agents),
                    "queue_size": self._queue.qsize(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            logger.debug("Failed to publish orchestrator status", exc_info=True)
