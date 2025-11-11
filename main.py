# Standard library imports
import json
import logging
import os
import signal
import socket
import sys
import threading
import time
import warnings

# Third-party imports
import paho.mqtt.client as mqtt

# Local imports
from modules.api import start_api
from modules.commands import run_predefined_command
from modules.config import (
    API_MOD,
    API_PORT,
    GAME_AGENT,
    GAME_FILE,
    MEDIA_AGENT,
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
from modules.deployment import notify_pipeline
from modules.desktop_agent import get_system_info, publish_discovery, start_desktop_agent
from modules.game_agent import start_game_agent
from modules.updater import UpdateManager

# ----------------------------
# Logging Configuration
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] (%(levelname)s) %(module)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


# ----------------------------
# MQTT Client
# ----------------------------

# Ignore deprecated mqtt callback version
warnings.filterwarnings("ignore", category=DeprecationWarning)

client = mqtt.Client()
exit_flag = threading.Event()

# Global list to track stop events for all threads
stop_events = []

# Global list to track additional subscriptions for reconnection
additional_subscriptions = []


# ----------------------------
# Connection State Management
# ----------------------------

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
            logger.info(f"Connection established (total connections: {self.connection_count})")

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


# ----------------------------
# MQTT Connection Functions
# ----------------------------

def connect_with_retry(client, broker, port, max_retries=10, initial_delay=1, max_delay=60):
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

        # Publish/republish discovery
        publish_discovery(client, device_id, base_topic, discovery_prefix, device_info)
    else:
        logger.error(message)
        conn_state.on_disconnected()


# ----------------------------
# MQTT Command Handler
# ----------------------------

def on_mqtt_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        command_key = payload.get("command")
        if not command_key:
            logger.warning("Received MQTT command message with no command key")
            return
        result = run_predefined_command(command_key)
        client.publish(f"{base_topic}/run_result", json.dumps(result), qos=1)
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding MQTT command payload: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Error handling MQTT command: {e}", exc_info=True)


# ----------------------------
# Media Agent Handler
# ----------------------------

def media_agent(client, stop_event):
    try:
        sysinfo = get_system_info()
        if sysinfo["os"] == "Linux":
            from modules.media_agent_linux import start_media_agent
            start_media_agent(client, stop_event)
        elif sysinfo["os"] == "Windows":
            logger.warning("Media agent is enabled but must be run standalone on Windows.")
            #from modules.media_agent import start_media_agent
    except Exception as e:
        logger.error(f"Error in media agent: {e}", exc_info=True)
    

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
    client.reconnect_delay_set(min_delay=MQTT_MIN_RECONNECT_DELAY, max_delay=MQTT_MAX_RECONNECT_DELAY)

    # Connect with retry logic
    logger.info("Initiating connection to MQTT broker...")
    if not connect_with_retry(client, MQTT_BROKER, MQTT_PORT, max_retries=MQTT_MAX_RETRIES):
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

    # Register message callback for commands (subscription happens in on_connect)
    client.message_callback_add(f"{base_topic}/run", on_mqtt_message)

    # Start desktop agent
    desktop_stop_event = threading.Event()
    stop_events.append(desktop_stop_event)
    desktop_thread = threading.Thread(
        target=start_desktop_agent,
        args=(client, base_topic, PUBLISH_INT, desktop_stop_event),
        name="DesktopAgent-Monitor",
        daemon=True
    )
    desktop_thread.start()
    logger.info("Desktop agent thread started")

    # Start API
    if API_MOD:
        api_stop_event = threading.Event()
        stop_events.append(api_stop_event)
        api_thread = threading.Thread(
            target=start_api,
            args=(API_PORT, api_stop_event),
            name="API-Server",
            daemon=True
        )
        api_thread.start()
        logger.info("API server thread started")

    # Start media agent
    if MEDIA_AGENT:
        media_stop_event = threading.Event()
        stop_events.append(media_stop_event)
        media_thread = threading.Thread(
            target=media_agent,
            args=(client, media_stop_event),
            name="MediaAgent-Monitor",
            daemon=True
        )
        media_thread.start()
        logger.info("Media agent thread started")

    # Start game agent
    if GAME_AGENT:
        game_stop_event = threading.Event()
        stop_events.append(game_stop_event)
        game_thread = threading.Thread(
            target=start_game_agent,
            args=(client, GAME_FILE, game_stop_event),
            name="GameAgent-Monitor",
            daemon=True
        )
        game_thread.start()
        logger.info("Game agent thread started")

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
    if '--deploy' in sys.argv:
        logger.info("Deploy mode detected, waiting 60s before notifying pipeline")
        time.sleep(60)
        notify_pipeline("Build Successful")

    # Keep main thread alive
    logger.info("Agent running. Press Ctrl+C to exit.")
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
