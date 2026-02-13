"""Output router — routes agent output to configured channels."""

import logging
from typing import Any

import httpx

logger = logging.getLogger("elmer.agents.output_router")

_TELEGRAM_API = "https://api.telegram.org"
_TELEGRAM_TIMEOUT = 15.0
_TELEGRAM_MAX_LENGTH = 4096

# Agent-specific display prefixes.
_AGENT_ICONS: dict[str, str] = {
    "daily-briefing": "\u2600\ufe0f",
    "weekly-digest": "\U0001f4ca",
    "node-watchdog": "\U0001f6a8",
    "allstar-monitor": "\U0001f4e1",
    "home-assistant-reactor": "\U0001f3e0",
    "meshtastic-responder": "\U0001f4f6",
    "knowledge-curator": "\U0001f4da",
    "radio-assistant": "\U0001f4fb",
    "system-monitor": "\U0001f5a5",
}

# Alert-type agents get a prominent header.
_ALERT_AGENTS = {"node-watchdog", "home-assistant-reactor", "allstar-monitor"}


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

    def _format_telegram_message(
        self, agent_name: str, response_text: str,
    ) -> str:
        """Format agent output for Telegram with per-agent styling."""
        icon = _AGENT_ICONS.get(agent_name, "\U0001f916")
        display_name = agent_name.replace("-", " ").title()

        if agent_name in _ALERT_AGENTS:
            header = f"{icon} *{display_name} Alert*"
        else:
            header = f"{icon} *{display_name}*"

        return f"{header}\n\n{response_text}"

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

        message = self._format_telegram_message(agent_name, response_text)

        # Split long messages into chunks for Telegram's 4096-char limit.
        chunks = self._split_message(message, _TELEGRAM_MAX_LENGTH - 100)

        url = f"{_TELEGRAM_API}/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=_TELEGRAM_TIMEOUT) as client:
            for chunk in chunks:
                payload = {
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "Markdown",
                }
                resp = await client.post(url, json=payload)
                data = resp.json()
                if not data.get("ok"):
                    # Retry without parse_mode if Markdown fails.
                    payload.pop("parse_mode", None)
                    await client.post(url, json=payload)

    @staticmethod
    def _split_message(text: str, max_len: int) -> list[str]:
        """Split text into chunks that fit within max_len."""
        if len(text) <= max_len:
            return [text]

        chunks: list[str] = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break

            # Try to split at a paragraph break.
            split_at = text.rfind("\n\n", 0, max_len)
            if split_at == -1:
                # Fall back to line break.
                split_at = text.rfind("\n", 0, max_len)
            if split_at == -1:
                # Fall back to space.
                split_at = text.rfind(" ", 0, max_len)
            if split_at == -1:
                split_at = max_len

            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")

        return chunks

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
