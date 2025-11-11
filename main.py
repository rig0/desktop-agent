# Standard library imports
import json
import logging
import os
import signal
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
    format='[%(asctime)s][%(levelname)s][%(name)s] - %(message)s'
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

def on_connect(client, userdata, flags, rc):
    messages = {
        0: "MQTT connected successfully.",
        1: "MQTT connection refused - incorrect protocol version.",
        2: "MQTT connection refused - invalid client identifier.",
        3: "MQTT connection refused - server unavailable.",
        4: "MQTT connection refused - bad username or password.",
        5: "MQTT connection refused - not authorized.",
    }
    message = messages.get(rc, f"MQTT connection failed with unknown error (code {rc}).")

    if rc == 0:
        logger.info(message)
    else:
        logger.error(message)

    if rc != 0:
        exit_flag.set()  # signal main thread to exit
        client.disconnect()
        return

    publish_discovery(client, device_id, base_topic, discovery_prefix, device_info)


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

    # Connect to MQTT Broker
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect

    # Cleanly handle MQTT connection errors
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        logger.error(f"Could not connect to MQTT broker: {e}", exc_info=True)
        sys.exit(1)

    # Listen for commands called via MQTT
    client.subscribe(f"{base_topic}/run")
    client.message_callback_add(f"{base_topic}/run", on_mqtt_message)

    # Start MQTT loop
    mqtt_thread = threading.Thread(
        target=client.loop_forever,
        name="Main-MQTT",
        daemon=True
    )
    mqtt_thread.start()
    logger.info("MQTT client thread started")

    # Wait briefly to see if connection fails
    for _ in range(20):  # up to ~2 seconds
        if exit_flag.is_set():
            logger.error("Exiting due to MQTT connection failure")
            sys.exit(1)
        time.sleep(0.1)

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

        client.subscribe(install_topic)
        client.message_callback_add(install_topic, on_update_install)
        update_manager.start()
        logger.info("Update manager started")

    # Trigger jenkins pipeline if deploying
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
        time.sleep(2)
        client.disconnect()
        sys.exit(0)

if __name__ == "__main__":
    main()
