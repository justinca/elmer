"""MQTT client helpers for Elmer services."""

import os

import paho.mqtt.client as mqtt


def create_client(
    client_id: str,
    host: str | None = None,
    port: int | None = None,
) -> mqtt.Client:
    """Create and configure an MQTT client.

    Args:
        client_id: Unique identifier for this client.
        host: MQTT broker hostname (defaults to MQTT_HOST env var).
        port: MQTT broker port (defaults to MQTT_PORT env var).

    Returns:
        A configured (but not yet connected) MQTT client.
    """
    host = host or os.getenv("MQTT_HOST", "localhost")
    port = port or int(os.getenv("MQTT_PORT", "1883"))

    client = mqtt.Client(
        client_id=client_id,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    client.connect(host, port)
    return client


def publish(client: mqtt.Client, topic: str, payload: str):
    """Publish a message to an MQTT topic."""
    client.publish(topic, payload)
