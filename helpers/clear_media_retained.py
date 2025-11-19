#!/usr/bin/env python3
"""
Clear retained MQTT messages for media monitor.

Use this script when the media monitor is showing stale data.
Run it on the affected PC to clear all retained messages for that device.

Usage:
    python helpers/clear_media_retained.py
"""

# System libraries
import sys
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Third-Party libraries
import paho.mqtt.client as mqtt  # noqa: E402

# Local Libraries
from core.config import (  # noqa: E402
    MQTT_BROKER,
    MQTT_PASS,
    MQTT_PORT,
    MQTT_USER,
    base_topic,
    device_id,
    discovery_prefix,
)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✓ Connected to MQTT broker at {MQTT_BROKER}")
    else:
        print(f"✗ Connection failed with code {rc}")
        sys.exit(1)


def clear_retained_messages(client):
    """Publish empty retained messages to clear old data."""

    topics_to_clear = [
        # Data topics
        f"{base_topic}/media/state",
        f"{base_topic}/media/attrs",
        f"{base_topic}/media/thumbnail",
        # Old discovery topics (in case they exist)
        f"{discovery_prefix}/sensor/{device_id}/media_status/config",
        f"{discovery_prefix}/camera/{device_id}/media/thumbnail/config",
        f"{discovery_prefix}/camera/{device_id}/media/thumbnail/config",  # Old nested format
        f"{discovery_prefix}/camera/{device_id}_media/config",  # Old flat format
    ]

    print("\nClearing retained messages...")
    for topic in topics_to_clear:
        result = client.publish(topic, payload=None, retain=True)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"  ✓ Cleared: {topic}")
        else:
            print(f"  ✗ Failed: {topic}")

    print("\n✓ All retained messages cleared!")
    print("\nNext steps:")
    print("1. Restart the media monitor")
    print("2. In Home Assistant, reload MQTT integration or restart HA")
    print("3. The media monitor will republish fresh discovery configs")


if __name__ == "__main__":
    print("=" * 60)
    print("Media Monitor - Clear Retained Messages")
    print("=" * 60)
    print(f"Device: {device_id}")
    print(f"Base topic: {base_topic}")
    print(f"Broker: {MQTT_BROKER}:{MQTT_PORT}")

    # Connect to MQTT
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        print(f"\n✗ Could not connect to MQTT broker: {e}")
        sys.exit(1)

    # Start loop to process connection
    client.loop_start()
    time.sleep(2)  # Wait for connection

    # Clear messages
    clear_retained_messages(client)

    # Wait a moment for messages to be published
    time.sleep(1)

    # Cleanup
    client.loop_stop()
    client.disconnect()

    print("\n" + "=" * 60)
