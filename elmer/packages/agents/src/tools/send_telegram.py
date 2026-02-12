"""Send Telegram tool — sends messages via the Telegram Bot API."""

import logging
from typing import Any

import httpx

from .base import BaseTool, ToolResult

logger = logging.getLogger("elmer.agents.tools.send_telegram")

_TELEGRAM_API = "https://api.telegram.org"
_TIMEOUT = 15.0


class SendTelegramTool(BaseTool):
    name = "send_telegram"
    description = "Send a message to the admin via Telegram."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message text to send",
                },
                "parse_mode": {
                    "type": "string",
                    "description": "Optional: Markdown or HTML",
                    "enum": ["Markdown", "HTML"],
                },
            },
            "required": ["message"],
        }

    async def execute(self, arguments: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        message = arguments.get("message", "")
        if not message.strip():
            return ToolResult(success=False, error="Empty message")

        settings = context["settings"]
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "")

        if not token:
            return ToolResult(success=False, error="TELEGRAM_BOT_TOKEN not configured")
        if not chat_id:
            return ToolResult(success=False, error="TELEGRAM_CHAT_ID not configured")

        parse_mode = arguments.get("parse_mode")
        payload: dict[str, Any] = {"chat_id": chat_id, "text": message}
        if parse_mode:
            payload["parse_mode"] = parse_mode

        url = f"{_TELEGRAM_API}/bot{token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()
                if data.get("ok"):
                    return ToolResult(success=True, data={"sent": True})
                return ToolResult(
                    success=False,
                    error=f"Telegram API error: {data.get('description', 'unknown')}",
                )
        except Exception as exc:
            return ToolResult(success=False, error=f"Telegram send failed: {exc}")
