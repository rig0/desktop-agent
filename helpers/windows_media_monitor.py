"""
Windows Media Monitor Wrapper Script.

This is a thin wrapper script designed specifically for Windows user-context execution.
It launches the media monitoring functionality by reusing the existing MediaMonitor
and MediaCollector infrastructure from the modules package.

Purpose:
    - Provides a standalone entry point for Windows Task Scheduler
    - Runs in user context to access Windows SMTC (System Media Transport Controls)
    - Reuses core monitoring and collection logic (no code duplication)

Architecture:
    This script imports and uses:
    - modules.monitors.media.MediaMonitor (core monitoring logic)
    - modules.collectors.media.MediaCollector (platform-specific collection)
    - modules.core.messaging.MessageBroker (MQTT abstraction)
    - modules.core.discovery.DiscoveryManager (Home Assistant discovery)
    - modules.core.config (centralized configuration)

Usage:
    python helpers/windows_media_monitor.py

Configuration:
    Reads from data/config.ini (same as main Desktop Agent)
    - [mqtt] section: broker, port, username, password
    - [device] section: name (for device_id)

Note:
    This replaces the functionality in modules/media_monitor.py for Windows
    environments. For backwards compatibility, the old
    modules/media_monitor.py remains untouched.
"""

# Standard library imports
import logging
import signal
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Third-party imports
import paho.mqtt.client as mqtt  # noqa: E402

# Local imports - reuse existing infrastructure
from modules.collectors.media import MediaCollector  # noqa: E402
from modules.core.config import (  # noqa: E402
    MQTT_BROKER,
    MQTT_PASS,
    MQTT_PORT,
    MQTT_USER,
    base_topic,
    device_id,
    device_info,
    discovery_prefix,
)
from modules.core.discovery import DiscoveryManager  # noqa: E402
from modules.core.messaging import MessageBroker  # noqa: E402
from modules.monitors.media import MediaMonitor  # noqa: E402

# ----------------------------
# Logging Configuration
# ----------------------------

# Create logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(module)s: %(message)s",
    datefmt="%m/%d/%Y %H:%M:%S",
)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Rotating file handler
file_handler = RotatingFileHandler(
    "data/windows_media_monitor.log",
    maxBytes=5 * 1024 * 1024,  # 5MB per file
    backupCount=3,  # Keep 3 backups
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# ----------------------------
# MQTT Connection
# ----------------------------


def on_connect(client, userdata, flags, rc):
    """MQTT connection callback."""
    if rc == 0:
        logger.info("Connected to MQTT broker successfully")
        # Publish availability
        client.publish(f"{base_topic}/availability", "online", qos=1, retain=True)
    else:
        logger.error(f"Failed to connect to MQTT broker, return code: {rc}")


def on_disconnect(client, userdata, rc):
    """MQTT disconnection callback."""
    if rc != 0:
        logger.warning(f"Unexpected disconnection from MQTT broker, code: {rc}")
    else:
        logger.info("Disconnected from MQTT broker")


# ----------------------------
# Main Entry Point
# ----------------------------


def main():
    """Main entry point for Windows media monitor."""
    logger.info("=" * 70)
    logger.info("Windows Media Monitor starting...")
    logger.info(f"Device: {device_id}")
    logger.info(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    logger.info(f"Base Topic: {base_topic}")
    logger.info("=" * 70)

    # Create stop event for graceful shutdown
    stop_event = threading.Event()

    def signal_handler(sig, frame):
        """Handle shutdown signals gracefully."""
        logger.info("Shutdown signal received, stopping media monitor...")
        stop_event.set()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Initialize MQTT client
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    # Set LWT (Last Will and Testament) for availability
    client.will_set(f"{base_topic}/availability", "offline", qos=1, retain=True)

    # Connect to MQTT broker
    try:
        logger.info(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    except Exception as e:
        logger.error(f"Failed to connect to MQTT broker: {e}", exc_info=True)
        logger.error("Exiting...")
        sys.exit(1)

    # Start MQTT network loop in background
    client.loop_start()
    logger.info("MQTT client loop started")

    # Create messaging and discovery infrastructure
    broker = MessageBroker(client, base_topic, discovery_prefix)
    discovery = DiscoveryManager(broker, device_id, device_info, base_topic)

    # Create media collector and monitor
    collector = MediaCollector()
    monitor = MediaMonitor(
        collector=collector, broker=broker, discovery=discovery, poll_interval=5
    )

    # Start monitoring in a separate thread
    monitor_thread = threading.Thread(
        target=monitor.start, args=(stop_event,), name="MediaMonitor", daemon=False
    )
    monitor_thread.start()
    logger.info("Media monitor thread started")

    # Keep main thread alive until stop_event is set
    try:
        monitor_thread.join()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
        stop_event.set()
        monitor_thread.join(timeout=5)

    # Cleanup: Publish offline availability
    logger.info("Publishing offline availability...")
    client.publish(f"{base_topic}/availability", "offline", qos=1, retain=True)

    # Stop MQTT loop and disconnect
    client.loop_stop()
    client.disconnect()

    logger.info("Windows Media Monitor stopped cleanly")
    logger.info("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Fatal error in Windows media monitor: {e}", exc_info=True)
        sys.exit(1)
