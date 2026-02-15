"""Agent executor — the runtime that actually runs agents.

Manages the tool-calling loop with Ollama, handles concurrency,
timeouts, and error recovery. Every failure is logged and recorded
in agent_runs without crashing the executor.
"""

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from .models import AgentDefinition
from .output_router import OutputRouter
from .tool_registry import get_registry
from .tools.base import ToolResult

logger = logging.getLogger("elmer.agents.executor")

_CHAT_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=10.0)
_MAX_TOOL_ROUNDS = 10
_MAX_TOOL_RESULT_CHARS = 4000
_DEFAULT_MAX_CONCURRENT = 5


class AgentExecutor:
    """Runs agents: builds context, calls Ollama with tools, executes
    tool calls, routes output, and manages the full run lifecycle."""

    def __init__(
        self,
        db: Any,
        settings: Any,
        mqtt_publish: Any,
    ) -> None:
        self._db = db
        self._settings = settings
        self._mqtt_publish = mqtt_publish
        self._tool_registry = get_registry()
        self._output_router = OutputRouter()
        self._agent_semaphores: dict[str, asyncio.Semaphore] = {}
        max_concurrent = getattr(settings, "AGENT_MAX_CONCURRENT", _DEFAULT_MAX_CONCURRENT)
        self._global_semaphore = asyncio.Semaphore(max_concurrent)

    async def execute(
        self,
        agent: AgentDefinition,
        run_id: int,
        trigger_data: dict[str, Any] | None = None,
        input_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an agent run. Updates the run record in the database."""
        trigger_data = trigger_data or {}
        input_data = input_data or {}

        # Acquire semaphores.
        agent_sem = self._get_agent_semaphore(agent.name, agent.max_concurrent)

        try:
            await asyncio.wait_for(
                self._acquire_both(agent_sem),
                timeout=float(agent.timeout_seconds),
            )
        except asyncio.TimeoutError:
            await self._complete_run(run_id, "timeout", error="Timed out waiting for execution slot")
            return {"error": "Timed out waiting for execution slot"}

        start_time = time.monotonic()
        try:
            # Mark as running.
            await self._update_run_status(run_id, "running")

            # Execute the agent within timeout.
            output = await asyncio.wait_for(
                self._run_agent(agent, trigger_data, input_data),
                timeout=float(agent.timeout_seconds),
            )

            # Complete the run.
            await self._complete_run(run_id, "completed", output_data=output)

            # Route output to configured channels.
            context = self._build_context(agent)
            await self._output_router.route(
                agent.name, agent.output_channels, output, context,
            )

            return output

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start_time
            error_msg = f"Execution timed out after {elapsed:.1f}s (limit: {agent.timeout_seconds}s)"
            logger.warning("Agent '%s' run %d: %s", agent.name, run_id, error_msg)
            await self._complete_run(run_id, "timeout", error=error_msg)
            return {"error": error_msg}

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.exception("Agent '%s' run %d failed", agent.name, run_id)
            await self._complete_run(run_id, "failed", error=error_msg)
            return {"error": error_msg}

        finally:
            agent_sem.release()
            self._global_semaphore.release()

    async def _run_agent(
        self,
        agent: AgentDefinition,
        trigger_data: dict[str, Any],
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Core agent execution: build context, call Ollama, handle tools."""
        context = self._build_context(agent)

        # Build tool instances.
        active_tools: dict[str, Any] = {}
        ollama_tools: list[dict[str, Any]] = []

        for agent_tool in agent.tools:
            tool_instance = self._tool_registry.create_instance(
                agent_tool.name, agent_tool.config,
            )
            if tool_instance is not None:
                active_tools[agent_tool.name] = tool_instance
                ollama_tools.append(tool_instance.to_ollama_tool())
            else:
                logger.warning("Unknown tool '%s' for agent '%s'", agent_tool.name, agent.name)

        # Build initial messages.
        system_content = agent.system_prompt or f"You are the {agent.display_name or agent.name} agent."

        # Auto-fetch knowledge context if the agent has search_knowledge.
        if "search_knowledge" in active_tools and input_data:
            query = self._extract_query(input_data)
            if query:
                try:
                    sk_tool = active_tools["search_knowledge"]
                    result = await sk_tool.execute({"query": query}, context)
                    if result.success and result.data:
                        results = result.data.get("results", [])
                        if results:
                            context_parts = []
                            for r in results[:3]:
                                source = r.get("source_path") or r.get("source", "")
                                context_parts.append(f"[{source}]\n{r['content']}")
                            knowledge_block = "\n\n".join(context_parts)
                            system_content += (
                                f"\n\nRelevant context from the knowledge base:\n\n{knowledge_block}"
                            )
                except Exception:
                    logger.warning("Auto knowledge fetch failed for agent '%s'", agent.name)

        user_content = self._format_input(input_data, trigger_data)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

        # Tool-calling loop.
        tool_calls_made: list[dict[str, Any]] = []
        final_response = ""
        steps = 0

        for step in range(_MAX_TOOL_ROUNDS):
            steps = step + 1

            # Call Ollama.
            llm_response = await self._call_ollama(
                agent.model, messages, ollama_tools if active_tools else None,
                temperature=agent.temperature,
            )

            msg = llm_response.get("message", {})
            msg_content = msg.get("content", "")
            msg_tool_calls = msg.get("tool_calls") or []

            if not msg_tool_calls:
                # No tool calls — this is the final response.
                final_response = msg_content
                break

            # Append the assistant message with tool calls to conversation.
            messages.append(msg)

            # Execute each tool call.
            for tc in msg_tool_calls:
                func = tc.get("function", {})
                func_name = func.get("name", "")
                func_args = func.get("arguments", {})

                # Arguments may be a string (JSON) or already parsed.
                if isinstance(func_args, str):
                    try:
                        func_args = json.loads(func_args)
                    except json.JSONDecodeError:
                        func_args = {"raw": func_args}

                tool_instance = active_tools.get(func_name)
                if tool_instance is None:
                    result = ToolResult(success=False, error=f"Unknown tool: {func_name}")
                else:
                    try:
                        result = await tool_instance.execute(func_args, context)
                    except Exception as exc:
                        result = ToolResult(success=False, error=f"Tool error: {exc}")

                # Record the tool call.
                tool_calls_made.append({
                    "tool": func_name,
                    "arguments": func_args,
                    "success": result.success,
                    "error": result.error,
                })

                # Send result back to Ollama.
                result_content = json.dumps(
                    result.data if result.success else {"error": result.error},
                    default=str,
                )
                # Truncate large results.
                if len(result_content) > _MAX_TOOL_RESULT_CHARS:
                    result_content = result_content[:_MAX_TOOL_RESULT_CHARS] + "...[truncated]"

                messages.append({"role": "tool", "content": result_content})

                logger.info(
                    "Agent '%s' tool call: %s -> %s",
                    agent.name, func_name, "ok" if result.success else result.error,
                )
        else:
            # Exhausted max rounds — take the last content as response.
            final_response = final_response or "(Agent reached maximum tool call rounds)"

        return {
            "response": final_response,
            "tool_calls_made": tool_calls_made,
            "model": agent.model,
            "steps": steps,
        }

    # ------------------------------------------------------------------
    # Ollama LLM call
    # ------------------------------------------------------------------

    async def _call_ollama(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Send chat request to Ollama via worker, falling back to direct."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        if temperature is not None:
            payload["options"] = {"temperature": temperature}

        worker_url = (
            f"http://{self._settings.ELMER_WORKER_HOST}:"
            f"{self._settings.ELMER_WORKER_PORT}/llm/chat"
        )

        # Try worker first.
        try:
            async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
                resp = await client.post(worker_url, json=payload)
                data = resp.json()
                if data.get("error"):
                    raise RuntimeError(data["error"])
                msg = data.get("message", {})
                if msg and (msg.get("content") or msg.get("tool_calls")):
                    return data
                logger.warning("Worker returned empty chat response, trying Ollama direct")
        except (httpx.RequestError, RuntimeError) as exc:
            logger.warning("Worker chat failed (%s), falling back to Ollama direct", exc)

        # Fall back to direct Ollama.
        ollama_url = (
            f"http://{self._settings.OLLAMA_HOST}:"
            f"{self._settings.OLLAMA_PORT}/api/chat"
        )
        async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
            resp = await client.post(ollama_url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        if data.get("error"):
            raise RuntimeError(data["error"])

        return data

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_context(self, agent: AgentDefinition) -> dict[str, Any]:
        """Build the runtime context dict passed to tools and output router."""
        return {
            "db": self._db,
            "settings": self._settings,
            "mqtt_publish": self._mqtt_publish,
            "agent_name": agent.name,
            "agent_config": agent.config,
        }

    def _get_agent_semaphore(self, agent_name: str, max_concurrent: int) -> asyncio.Semaphore:
        """Get or create a per-agent semaphore."""
        if agent_name not in self._agent_semaphores:
            self._agent_semaphores[agent_name] = asyncio.Semaphore(max_concurrent)
        return self._agent_semaphores[agent_name]

    async def _acquire_both(self, agent_sem: asyncio.Semaphore) -> None:
        """Acquire both the per-agent and global semaphores."""
        await agent_sem.acquire()
        try:
            await self._global_semaphore.acquire()
        except Exception:
            agent_sem.release()
            raise

    async def _update_run_status(self, run_id: int, status: str) -> None:
        """Update the status of a run record."""
        try:
            await self._db.execute(
                "UPDATE elmer.agent_runs SET status = $1 WHERE id = $2",
                status, run_id,
            )
        except Exception:
            logger.warning("Failed to update run %d status to %s", run_id, status)

    async def _complete_run(
        self,
        run_id: int,
        status: str,
        output_data: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Mark a run as completed/failed/timeout."""
        try:
            await self._db.execute(
                """
                UPDATE elmer.agent_runs SET
                    status = $1,
                    output_data = $2::jsonb,
                    error = $3,
                    completed_at = now(),
                    duration_seconds = EXTRACT(EPOCH FROM (now() - started_at))
                WHERE id = $4
                """,
                status,
                json.dumps(output_data or {}, default=str),
                error,
                run_id,
            )
        except Exception:
            logger.exception("Failed to complete run %d", run_id)

    @staticmethod
    def _format_input(
        input_data: dict[str, Any],
        trigger_data: dict[str, Any],
    ) -> str:
        """Format input and trigger data into a user message."""
        parts: list[str] = []

        if trigger_data:
            trigger_type = trigger_data.get("type", "api")
            parts.append(f"[Triggered by: {trigger_type}]")

        # Extract the main message from input.
        message = (
            input_data.get("message")
            or input_data.get("question")
            or input_data.get("query")
            or input_data.get("text")
        )

        if message:
            parts.append(message)
        elif input_data:
            parts.append(json.dumps(input_data, default=str))
        else:
            parts.append("Please perform your default task.")

        return "\n".join(parts)

    @staticmethod
    def _extract_query(input_data: dict[str, Any]) -> str:
        """Extract a search query from input data."""
        return (
            input_data.get("message")
            or input_data.get("question")
            or input_data.get("query")
            or input_data.get("text")
            or ""
        )
