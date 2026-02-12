#!/usr/bin/env python3
"""Quick MQTT test — publishes a heartbeat and prints all elmer/# messages.

Usage:
    python scripts/mqtt-test.py                     # default localhost:1883
    python scripts/mqtt-test.py --host 192.168.1.5  # custom broker
    python scripts/mqtt-test.py --publish-only       # fire one heartbeat and exit
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

# Allow running from repo root without installing packages.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages"))

from common.src.mqtt import ElmerMQTTClient  # noqa: E402


async def _print_message(topic: str, payload: dict) -> None:
    """Pretty-print an incoming MQTT message."""
    ts = datetime.now().strftime("%H:%M:%S")
    pretty = json.dumps(payload, indent=2, default=str)
    print(f"[{ts}] {topic}")
    print(f"  {pretty}")
    print()


def _build_test_heartbeat(node: str = "test-node") -> dict:
    return {
        "node": node,
        "status": "online",
        "uptime_seconds": 42,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": {
            "platform": sys.platform,
            "hostname": "mqtt-test-script",
            "purpose": "testing MQTT connectivity",
        },
    }


async def main(args: argparse.Namespace) -> None:
    client = ElmerMQTTClient(
        host=args.host,
        port=args.port,
        username=args.user or None,
        password=args.password or None,
        client_id="elmer-mqtt-test",
    )

    if not args.publish_only:
        client.subscribe("elmer/#", _print_message)

    await client.connect()

    if not client.is_connected:
        print(f"Could not connect to MQTT broker at {args.host}:{args.port}")
        return

    print(f"Connected to MQTT broker at {args.host}:{args.port}")
    print()

    # Publish a test heartbeat.
    hb = _build_test_heartbeat(args.node)
    await client.publish_heartbeat(args.node, hb)
    print(f"Published test heartbeat to elmer/{args.node}/heartbeat")

    # Publish a test event.
    await client.publish_event("test", "mqtt_test", {"message": "hello from mqtt-test.py"})
    print(f"Published test event to elmer/events/test/mqtt_test")
    print()

    if args.publish_only:
        await asyncio.sleep(0.5)  # let the publish flush
        await client.disconnect()
        print("Done.")
        return

    print("Listening for messages on elmer/# (Ctrl+C to quit)...")
    print("=" * 60)
    print()

    try:
        await asyncio.Event().wait()  # block forever
    except asyncio.CancelledError:
        pass
    finally:
        await client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Elmer MQTT test tool")
    parser.add_argument("--host", default=os.getenv("MQTT_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    parser.add_argument("--user", default=os.getenv("MQTT_USER", ""))
    parser.add_argument("--password", default=os.getenv("MQTT_PASSWORD", ""))
    parser.add_argument("--node", default="test-node", help="Node name for test heartbeat")
    parser.add_argument("--publish-only", action="store_true", help="Publish and exit")
    args = parser.parse_args()

    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\nStopped.")
