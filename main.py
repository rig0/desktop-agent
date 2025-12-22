#!/usr/bin/env python3
"""Desktop Agent - System monitoring and integration for Home Assistant.

Desktop Agent collects system information from desktop computers and
exposes it via MQTT and REST API for integration with Home Assistant
and other automation platforms.

The application provides:
- Real-time system metrics (CPU, memory, disk, network, GPU)
- Media playback monitoring
- Game monitoring with IGDB metadata integration
- Remote command execution via MQTT & API
- REST API for external integrations
- Automatic Home Assistant MQTT discovery
- Self-updating capabilities

Architecture:
    The application follows a modular, layered architecture:

    1. **Core Layer** (modules/core/):
       - config: Configuration management
       - messaging: MQTT messaging abstraction
       - discovery: Home Assistant discovery management

    2. **Data Collection Layer** (modules/collectors/):
       - system: System metrics collection
       - game: Game information and metadata
       - media: Media playback information

    3. **Monitoring Layer** (modules/monitors/):
       - system: System monitoring
       - game: Game monitoring
       - media: Media playback monitoring

    4. **Feature Layer** (modules/):
       - api: REST API server
       - commands: Remote command execution
       - updater: Update manager

    5. **Utility Layer** (modules/utils/):
       - Platform detection, formatting, IGDB integration, etc.

MQTT Topics Structure:
    desktop/{device_id}/availability         - Online/offline status (LWT)
    desktop/{device_id}/state                - System state. All senors (JSON)
    desktop/{device_id}/{sensor}             - Individual sensor info
    desktop/{device_id}/game/state           - Game state (playing/idle)
    desktop/{device_id}/game/attrs           - Game metadata (JSON)
    desktop/{device_id}/game/cover           - Game cover image (binary)
    desktop/{device_id}/game/artwork         - Game artwork (binary)
    desktop/{device_id}/media/state          - Media state (playing/paused/idle)
    desktop/{device_id}/media/attrs          - Media attributes (JSON)
    desktop/{device_id}/media/thumbnail      - Media thumbnail (binary)
    desktop/{device_id}/run                  - Command execution (JSON)
    desktop/{device_id}/run_result           - Command result (JSON)
    desktop/{device_id}/update/state         - Update status (JSON)
    desktop/{device_id}/update/install       - Trigger update installation

Connection Management:
    - Automatic reconnection with exponential backoff
    - Last Will and Testament (LWT) for availability tracking
    - Connection state monitoring for thread coordination
    - Configurable retry limits and timeouts

Thread Safety:
    - All monitoring modules run in separate daemon threads
    - Thread-safe connection state management
    - Graceful shutdown via threading.Event signals
    - Clean disconnect on SIGINT/SIGTERM

Configuration:
    Configuration is loaded from data/config.ini with the following sections:
    - [device]: Device name and publishing interval
    - [mqtt]: MQTT broker connection settings
    - [modules]: Feature flags to enable/disable components
    - [api]: REST API configuration
    - [igdb]: IGDB API credentials for game metadata
    - [updates]: Update manager settings

Usage:
    python main.py              # Normal operation
    python main.py --deploy     # Deployment mode (notifies CI/CD pipeline) Devs only

Exit Codes:
    0: Clean shutdown
    1: Configuration error or connection failure

Example:
    >>> # main.py starts automatically when run
    >>> # Configuration loaded from data/config.ini
    >>> # MQTT connection established
    >>> # Monitoring threads started
    >>> # Application runs until SIGINT/SIGTERM

Repo: https://github.com/rig0/desktop-agent/
"""

# Standard library imports
import json
import logging
import signal
import socket
import sys
import threading
import time
import warnings
from logging.handlers import RotatingFileHandler

# Third-party imports
import paho.mqtt.client as mqtt

# Local imports
from modules.api import start_api
from modules.collectors.system import SystemInfoCollector
from modules.commands import run_predefined_command
from modules.core.config import (
    API_MOD,
    API_PORT,
    GAME_FILE,
    GAME_MONITOR,
    MEDIA_MONITOR,
    MQTT_BROKER,
    MQTT_CONNECTION_TIMEOUT,
    MQTT_MAX_RECONNECT_DELAY,
    MQTT_MAX_RETRIES,
    MQTT_MIN_RECONNECT_DELAY,
    MQTT_PASS,
    MQTT_PORT,
    MQTT_USER,
    PUBLISH_INT,
    UPDATES_AUTO,
    UPDATES_CH,
    UPDATES_INT,
    UPDATES_MOD,
    base_topic,
    device_id,
    device_info,
    discovery_prefix,
)
from modules.core.discovery import DiscoveryManager
from modules.core.messaging import MessageBroker
from modules.monitors.system import SystemMonitor
from modules.updater import UpdateManager
from modules.utils.deployment import notify_pipeline

# Conditional imports for optional features
if GAME_MONITOR:
    from modules.collectors.game import GameCollector
    from modules.monitors.game import GameMonitor

if MEDIA_MONITOR:
    from modules.collectors.media import MediaCollector
    from modules.monitors.media import MediaMonitor


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
    "data/main.log",
    maxBytes=5 * 1024 * 1024,  # 5MB per file
    backupCount=3,  # Keep 3 backups (main.log.1, main.log.2, main.log.3)
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


# ----------------------------
# MQTT Client
# ----------------------------

# Ignore deprecated mqtt callback version
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Initialize mqtt client
client = mqtt.Client()
exit_flag = threading.Event()

# Global list to track stop events for all threads
stop_events = []

# Global list to track additional subscriptions for reconnection
additional_subscriptions = []


class ConnectionState:
    """Track MQTT connection state for monitoring and thread coordination."""

    def __init__(self):
        self.connected = threading.Event()
        self.connection_count = 0
        self.last_disconnect_time = None
        self.lock = threading.Lock()

    def on_connected(self):
        """Mark as connected."""
        with self.lock:
            self.connected.set()
            self.connection_count += 1
            logger.info(
                f"Connection established (total connections: {self.connection_count})"
            )

    def on_disconnected(self):
        """Mark as disconnected."""
        with self.lock:
            self.connected.clear()
            self.last_disconnect_time = time.time()
            logger.warning("Connection lost")

    def wait_for_connection(self, timeout=None):
        """Block until connected or timeout. Returns True if connected."""
        return self.connected.wait(timeout)

    def is_connected(self):
        """Check if currently connected."""
        return self.connected.is_set()


def connect_with_retry(
    client, broker, port, max_retries=10, initial_delay=1, max_delay=60
):
    """
    Connect to MQTT broker with exponential backoff retry logic.

    Args:
        client: MQTT client instance
        broker: MQTT broker hostname/IP
        port: MQTT broker port
        max_retries: Maximum retry attempts (None = infinite)
        initial_delay: Initial retry delay in seconds
        max_delay: Maximum retry delay in seconds

    Returns:
        bool: True if connection initiated successfully
    """
    retry_count = 0
    delay = initial_delay

    while max_retries is None or retry_count < max_retries:
        try:
            logger.info(f"Attempting to connect to MQTT broker at {broker}:{port}...")
            client.connect(broker, port, keepalive=60)
            logger.info("MQTT connection initiated successfully")
            return True

        except (ConnectionRefusedError, OSError, socket.error) as e:
            retry_count += 1
            if max_retries is not None and retry_count >= max_retries:
                logger.error(f"Failed to connect after {retry_count} attempts: {e}")
                return False

            logger.warning(f"Connection attempt {retry_count} failed: {e}")
            logger.info(f"Retrying in {delay} seconds...")
            time.sleep(delay)

            # Exponential backoff with max cap
            delay = min(delay * 2, max_delay)

    return False


def on_disconnect(client, userdata, rc):
    """
    Handle MQTT disconnection with logging.

    Disconnect codes:
        0: Clean disconnect
        1-255: Unexpected disconnect
    """
    conn_state.on_disconnected()

    if rc == 0:
        logger.info("MQTT client disconnected cleanly")
        return

    # Unexpected disconnect
    disconnect_reasons = {
        1: "Protocol version error",
        2: "Client identifier error",
        3: "Server unavailable",
        4: "Bad username or password",
        5: "Not authorized",
        7: "Connection lost",
    }

    reason = disconnect_reasons.get(rc, f"Unknown reason (code {rc})")
    logger.warning(f"MQTT disconnected unexpectedly: {reason}")
    logger.info("Automatic reconnection will be attempted by MQTT client...")


def on_connect(client, userdata, flags, rc):
    """Handle MQTT connection with retry logic."""
    messages = {
        0: "MQTT connected successfully",
        1: "MQTT connection refused - incorrect protocol version",
        2: "MQTT connection refused - invalid client identifier",
        3: "MQTT connection refused - server unavailable",
        4: "MQTT connection refused - bad username or password",
        5: "MQTT connection refused - not authorized",
    }
    message = messages.get(rc, f"MQTT connection failed with unknown error (code {rc})")

    if rc == 0:
        logger.info(message)
        conn_state.on_connected()

        # Publish online status (LWT will publish offline on disconnect)
        availability_topic = f"{base_topic}/availability"
        client.publish(availability_topic, "online", qos=1, retain=True)

        # Re-subscribe to topics (important for reconnection scenarios)
        client.subscribe(f"{base_topic}/run")
        logger.info(f"Subscribed to command topic: {base_topic}/run")

        # Re-subscribe to any additional topics (e.g., update install)
        for topic in additional_subscriptions:
            client.subscribe(topic)
            logger.info(f"Re-subscribed to topic: {topic}")

    else:
        logger.error(message)
        conn_state.on_disconnected()


def on_mqtt_message(client, userdata, msg):
    """Handle MQTT commannds"""
    try:
        # Load message
        payload = json.loads(msg.payload.decode())
        # Extract command
        command_key = payload.get("command")
        if not command_key:
            logger.warning("Received MQTT command message with no command key")
            return
        # Run command and return result
        result = run_predefined_command(command_key)
        client.publish(f"{base_topic}/run_result", json.dumps(result), qos=1)
    # Handle errors
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding MQTT command payload: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Error handling MQTT command: {e}", exc_info=True)


# ----------------------------
# Signal Handlers
# ----------------------------


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Shutdown signal received, stopping all threads...")
    exit_flag.set()
    for stop_event in stop_events:
        stop_event.set()

    # Give threads time to clean up
    time.sleep(2)
    logger.info("Shutdown complete")
    sys.exit(0)


# ----------------------------
# Main
# ----------------------------


def main():
    """
    Main entry point for Desktop Agent application.

    Initializes and starts all components:
    1. Registers signal handlers for graceful shutdown
    2. Creates connection state tracker
    3. Configures MQTT client with authentication and LWT
    4. Connects to MQTT broker with retry logic
    5. Starts MQTT client loop
    6. Creates core infrastructure (MessageBroker, DiscoveryManager)
    7. Starts monitoring threads (system, game, media as configured)
    8. Starts optional features (API, updates as configured)
    9. Enters main event loop until shutdown signal received

    The application runs continuously until:
    - SIGINT (Ctrl+C) is received
    - SIGTERM is received
    - A fatal error occurs

    On shutdown:
    - Signals all threads to stop via stop_events
    - Publishes offline status to MQTT
    - Stops MQTT client loop
    - Disconnects from MQTT broker
    - Exits with code 0

    Raises:
        SystemExit: On fatal configuration or connection errors (exit code 1)
    """
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Starting Desktop Agent...")

    # Create connection state tracker
    global conn_state
    conn_state = ConnectionState()

    # Configure MQTT client
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    # Set Last Will and Testament (published automatically on unexpected disconnect)
    availability_topic = f"{base_topic}/availability"
    client.will_set(availability_topic, payload="offline", qos=1, retain=True)
    logger.info("Last Will and Testament configured")

    # Configure automatic reconnection
    client.reconnect_delay_set(
        min_delay=MQTT_MIN_RECONNECT_DELAY, max_delay=MQTT_MAX_RECONNECT_DELAY
    )

    # Connect with retry logic
    logger.info("Initiating connection to MQTT broker...")
    if not connect_with_retry(
        client, MQTT_BROKER, MQTT_PORT, max_retries=MQTT_MAX_RETRIES
    ):
        logger.error("Failed to connect to MQTT broker after maximum retry attempts")
        sys.exit(1)

    # Start MQTT loop (handles automatic reconnection in background)
    client.loop_start()
    logger.info("MQTT client loop started")

    # Wait for initial connection to be established
    logger.info("Waiting for MQTT connection to be established...")
    if not conn_state.wait_for_connection(timeout=MQTT_CONNECTION_TIMEOUT):
        logger.error("Timed out waiting for MQTT connection")
        client.loop_stop()
        sys.exit(1)

    logger.info("MQTT connection established, starting modules...")

    # Create core infrastructure
    broker = MessageBroker(client, base_topic, discovery_prefix)
    discovery = DiscoveryManager(broker, device_id, device_info, base_topic)

    # Register message callback for commands (subscription happens in on_connect)
    client.message_callback_add(f"{base_topic}/run", on_mqtt_message)

    # Start system monitor
    system_collector = SystemInfoCollector()
    system_monitor = SystemMonitor(
        system_collector, broker, discovery, device_id, base_topic, PUBLISH_INT
    )
    system_stop_event = threading.Event()
    stop_events.append(system_stop_event)
    system_thread = threading.Thread(
        target=system_monitor.start,
        args=(system_stop_event,),
        name="SystemMonitor",
        daemon=True,
    )
    system_thread.start()
    logger.info("System monitor started")

    # Start API
    if API_MOD:
        api_stop_event = threading.Event()
        stop_events.append(api_stop_event)
        api_thread = threading.Thread(
            target=start_api,
            args=(API_PORT, api_stop_event),
            name="API-Server",
            daemon=True,
        )
        api_thread.start()
        logger.info("API server started")

    # Start media monitor
    if MEDIA_MONITOR:
        media_collector = MediaCollector()
        media_monitor = MediaMonitor(media_collector, broker, discovery)
        media_stop_event = threading.Event()
        stop_events.append(media_stop_event)
        media_thread = threading.Thread(
            target=media_monitor.start,
            args=(media_stop_event,),
            name="MediaMonitor",
            daemon=True,
        )
        media_thread.start()
        logger.info("Media monitor started")

    # Start game monitor
    if GAME_MONITOR:
        game_collector = GameCollector(GAME_FILE)
        game_monitor = GameMonitor(game_collector, broker, discovery, GAME_FILE)
        game_stop_event = threading.Event()
        stop_events.append(game_stop_event)
        game_thread = threading.Thread(
            target=game_monitor.start,
            args=(game_stop_event,),
            name="GameMonitor",
            daemon=True,
        )
        game_thread.start()
        logger.info("Game monitor started")

    # Start updater monitor
    update_manager = None
    if UPDATES_MOD:
        update_stop_event = threading.Event()
        stop_events.append(update_stop_event)

        update_manager = UpdateManager(
            client=client,
            base_topic=base_topic,
            discovery_prefix=discovery_prefix,
            device_id=device_id,
            device_info=device_info,
            channel=UPDATES_CH,
            interval=UPDATES_INT,
            auto_install=UPDATES_AUTO,
            stop_event=update_stop_event,
        )

        install_topic = f"{base_topic}/update/install"

        def on_update_install(client, userdata, msg):
            try:
                update_manager.handle_install_request(msg.payload)
            except Exception as e:
                logger.error(f"Error handling update install request: {e}", exc_info=True)

        # Add to additional subscriptions for reconnection handling
        additional_subscriptions.append(install_topic)

        # Subscribe initially (will also happen on reconnect via on_connect)
        client.subscribe(install_topic)
        client.message_callback_add(install_topic, on_update_install)
        update_manager.start()
        logger.info("Update manager started")

    # Trigger Jenkins pipeline if deploying
    if "--deploy" in sys.argv:
        logger.info("Deploy mode detected, waiting 60s before notifying pipeline")
        time.sleep(60)
        notify_pipeline("Build Successful")

    # Keep main thread alive
    logger.info("=" * 50)
    logger.info("Desktop Agent running. Press Ctrl+C to exit...")
    logger.info(f"Device: {device_id}")
    logger.info(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    logger.info(f"Base Topic: {base_topic}")
    logger.info("=" * 50)
    try:
        while not exit_flag.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
        exit_flag.set()
        for stop_event in stop_events:
            stop_event.set()

        # Publish offline status before disconnecting
        logger.info("Publishing offline status...")
        client.publish(availability_topic, "offline", qos=1, retain=True)
        time.sleep(0.5)  # Brief delay to ensure message is sent

        # Stop MQTT loop and disconnect
        client.loop_stop()
        client.disconnect()

        time.sleep(1)
        sys.exit(0)


if __name__ == "__main__":
    main()
