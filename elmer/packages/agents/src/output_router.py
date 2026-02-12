"""Output router — routes agent output to configured channels."""

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger("elmer.agents.output_router")

_TELEGRAM_API = "https://api.telegram.org"
_TELEGRAM_TIMEOUT = 15.0


class OutputRouter:
    """Routes agent output to one or more delivery channels."""

    async def route(
        self,
        agent_name: str,
        channels: list[str],
        output: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        """Send output to each configured channel. Errors are logged, not raised."""
        for channel in channels:
            try:
                await self._send(channel, agent_name, output, context)
            except Exception:
                logger.warning(
                    "Failed to route output to '%s' for agent '%s'",
                    channel, agent_name, exc_info=True,
                )

    async def _send(
        self,
        channel: str,
        agent_name: str,
        output: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        if channel == "telegram":
            await self._send_telegram(agent_name, output, context)
        elif channel == "mqtt":
            await self._send_mqtt(agent_name, output, context)
        elif channel == "dashboard":
            pass  # Already stored in agent_runs.output_data
        elif channel == "log":
            self._send_log(agent_name, output)
        else:
            logger.warning("Unknown output channel: %s", channel)

    async def _send_telegram(
        self,
        agent_name: str,
        output: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        settings = context["settings"]
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "")

        if not token or not chat_id:
            logger.debug("Telegram not configured, skipping output routing")
            return

        response_text = output.get("response", "")
        if not response_text:
            return

        # Format message with agent header.
        message = f"*{agent_name}*\n\n{response_text}"

        # Truncate for Telegram's 4096-char limit.
        if len(message) > 4000:
            message = message[:3997] + "..."

        url = f"{_TELEGRAM_API}/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}

        async with httpx.AsyncClient(timeout=_TELEGRAM_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            if not data.get("ok"):
                # Retry without parse_mode if Markdown fails.
                payload.pop("parse_mode", None)
                await client.post(url, json=payload)

    async def _send_mqtt(
        self,
        agent_name: str,
        output: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        mqtt_publish = context.get("mqtt_publish")
        if mqtt_publish is None:
            return

        topic = f"elmer/agents/{agent_name}/output"
        await mqtt_publish(topic, output)

    @staticmethod
    def _send_log(agent_name: str, output: dict[str, Any]) -> None:
        agent_logger = logging.getLogger(f"elmer.agents.{agent_name}")
        response = output.get("response", "")
        steps = output.get("steps", 0)
        tool_calls = output.get("tool_calls_made", [])
        agent_logger.info(
            "Run complete (%d steps, %d tool calls): %s",
            steps, len(tool_calls), response[:200],
        )
