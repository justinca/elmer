"""Publish MQTT tool — publishes messages to MQTT topics."""

import json
import logging
from typing import Any

from .base import BaseTool, ToolResult

logger = logging.getLogger("elmer.agents.tools.publish_mqtt")


class PublishMQTTTool(BaseTool):
    name = "publish_mqtt"
    description = "Publish a message to an MQTT topic."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "MQTT topic to publish to",
                },
                "payload": {
                    "type": "string",
                    "description": "Message payload (JSON string or plain text)",
                },
            },
            "required": ["topic", "payload"],
        }

    async def execute(self, arguments: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        agent_name = context.get("agent_name", "unknown")
        default_topic = self.config.get("topic", f"elmer/agents/{agent_name}/output")

        topic = arguments.get("topic") or default_topic
        payload_str = arguments.get("payload", "")

        # Security: only allow elmer/ topic prefix.
        if not topic.startswith("elmer/"):
            return ToolResult(success=False, error="Topic must start with 'elmer/'")

        # Try to parse as JSON, otherwise send as-is.
        try:
            payload = json.loads(payload_str)
        except (json.JSONDecodeError, TypeError):
            payload = payload_str

        mqtt_publish = context.get("mqtt_publish")
        if mqtt_publish is None:
            return ToolResult(success=False, error="MQTT not available")

        try:
            await mqtt_publish(topic, payload)
            return ToolResult(success=True, data={"topic": topic, "published": True})
        except Exception as exc:
            return ToolResult(success=False, error=f"MQTT publish failed: {exc}")
