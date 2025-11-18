# Standard library imports
import asyncio
import json
import logging
import sys
import threading
import time
from pathlib import Path

# Third-party imports
import paho.mqtt.client as mqtt
from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
)

# Configure logger
logger = logging.getLogger(__name__)

# Local imports
# Attempt relative import for use as a module within a package structure
try:
    from .config import (  # PUBLISH_INT,
        DEVICE_NAME,
        MQTT_BROKER,
        MQTT_PASS,
        MQTT_PORT,
        MQTT_USER,
        base_topic,
        device_id,
        device_info,
        discovery_prefix,
    )
# Fall back to direct import which assumes the script is being ran standalone
except ImportError:
    from config import (  # PUBLISH_INT,
        DEVICE_NAME,
        MQTT_BROKER,
        MQTT_PASS,
        MQTT_PORT,
        MQTT_USER,
        base_topic,
        device_id,
        device_info,
        discovery_prefix,
    )


# ----------------------------
# Windows Media Monitor (SMTC)
# ----------------------------


async def _get_media_info_async():
    sessions = await MediaManager.request_async()
    current = sessions.get_current_session()
    if not current:
        return None

    props = await current.try_get_media_properties_async()
    title = getattr(props, "title", "") or ""
    artist = getattr(props, "artist", "") or ""
    album = getattr(props, "album_title", "") or ""

    # Get thumbnail bytes if available
    thumbnail_bytes = None
    if getattr(props, "thumbnail", None) is not None:
        try:
            stream = await props.thumbnail.open_read_async()
            size = int(stream.size or 0)
            if size > 0:
                from winsdk.windows.storage.streams import DataReader

                input_stream = stream.get_input_stream_at(0)
                reader = DataReader(input_stream)
                await reader.load_async(size)
                buffer = reader.read_buffer(size)
                byte_array = bytearray(size)
                DataReader.from_buffer(buffer).read_bytes(byte_array)
                thumbnail_bytes = bytes(byte_array)
        except Exception as e:
            logger.error(f"Failed to read thumbnail: {e}", exc_info=True)

    playback = current.get_playback_info()
    status = int(playback.playback_status)
    is_playing = status == 4

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "is_playing": is_playing,
        "playback_status": status,
        "thumbnail_bytes": thumbnail_bytes,
    }


def get_media_info():
    try:
        return asyncio.run(_get_media_info_async())
    except Exception as e:
        logger.error(f"Error getting media info: {e}", exc_info=True)
        return None


def start_media_monitor(client: mqtt.Client, stop_event):
    # Starts the media polling thread and publishes discovery.
    def media_poller():
        logger.info("Media Monitor poller thread started")
        last_attrs = None
        last_image = None
        BASE_DIR = Path(__file__).parent.parent
        placeholder_path = BASE_DIR / "resources" / "media_thumb.png"
        placeholder_path_custom = BASE_DIR / "data" / "media_monitor" / "media_thumb.png"

        try:
            while not stop_event.is_set():
                try:
                    info = get_media_info()
                    if info:
                        state = (
                            "playing"
                            if info["is_playing"]
                            else "paused"
                            if info["playback_status"] == 5
                            else "idle"
                        )
                        attrs = {
                            "title": info["title"],
                            "artist": info["artist"],
                            "album": info["album"],
                            "status": state,
                        }

                        client.publish(f"{base_topic}/media/state", state, retain=True)

                        if attrs != last_attrs:
                            client.publish(
                                f"{base_topic}/media/attrs",
                                json.dumps(attrs),
                                retain=True,
                            )
                            last_attrs = attrs

                        # Thumbnail or placeholder
                        thumbnail_bytes = info.get("thumbnail_bytes")
                        if not thumbnail_bytes:
                            # Try custom placeholder first
                            if placeholder_path_custom.exists():
                                try:
                                    with open(placeholder_path_custom, "rb") as f:
                                        thumbnail_bytes = f.read()
                                except (IOError, OSError) as e:
                                    logger.debug(f"No custom thumbnail detected: {e}")

                            # Fallback to default placeholder if needed
                            if not thumbnail_bytes and placeholder_path.exists():
                                try:
                                    with open(placeholder_path, "rb") as f:
                                        thumbnail_bytes = f.read()
                                except (IOError, OSError) as e:
                                    logger.error(
                                        f"Failed to load default placeholder thumbnail: {e}"
                                    )
                                    thumbnail_bytes = None

                        if thumbnail_bytes and thumbnail_bytes != last_image:
                            client.publish(
                                f"{base_topic}/media/thumbnail",
                                thumbnail_bytes,
                                retain=True,
                            )
                            last_image = thumbnail_bytes

                except Exception as e:
                    logger.error(f"Error in media poller: {e}", exc_info=True)

                # Sleep but allow interruption
                stop_event.wait(5)
        except Exception as e:
            logger.critical(
                f"Fatal error in Media Monitor poller thread: {e}", exc_info=True
            )
        finally:
            logger.info("Media Monitor poller thread stopped")

    def publish_discovery():
        try:
            # Simple media state sensor
            sensor_payload = {
                "name": "Media Status",
                "state_topic": f"{base_topic}/media/state",
                "icon": "mdi:multimedia",
                "unique_id": f"{device_id}_media_status",
                "device": device_info,
                "availability_topic": f"{base_topic}/availability",
                "json_attributes_topic": f"{base_topic}/media/attrs",
            }

            topic = f"{discovery_prefix}/sensor/{device_id}/media_status/config"
            client.publish(topic, json.dumps(sensor_payload), retain=True)
            logger.debug("Published discovery for media status")

            # Camera-style media thumbnail
            camera_payload = {
                "platform": "mqtt",
                "name": f"{DEVICE_NAME} Media",
                "unique_id": f"{device_id}_media",
                "device": device_info,
                "availability_topic": f"{base_topic}/availability",
                "topic": f"{base_topic}/media/thumbnail",
                "icon": "mdi:music",
            }
            topic = f"{discovery_prefix}/camera/{device_id}_media/config"
            client.publish(topic, json.dumps(camera_payload), retain=True)
            logger.debug("Published discovery for media camera")
            logger.info("Published discovery for media agent entities")
        except Exception as e:
            logger.error(f"Error publishing media agent discovery: {e}", exc_info=True)

    publish_discovery()
    threading.Thread(target=media_poller, name="MediaAgent-Poller", daemon=True).start()


def on_connect(client, userdata, flags, rc):
    logger.info(f"Connected to MQTT broker with result code {rc}")


if __name__ == "__main__":
    import signal

    # Configure logging for standalone execution
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] (%(levelname)s) %(module)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info("Starting Media Monitor in standalone mode (Windows)...")

    # Create stop event for graceful shutdown
    stop_event = threading.Event()

    def signal_handler(sig, frame):
        """Handle shutdown signals gracefully."""
        logger.info("Shutdown signal received, stopping media agent...")
        stop_event.set()
        time.sleep(1)
        client.disconnect()
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Connect to MQTT
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        logger.error(f"Could not connect to MQTT broker: {e}", exc_info=True)
        sys.exit(1)

    # Start MQTT loop in background
    client.loop_start()
    logger.info("MQTT client loop started")

    # Start media monitor with stop_event
    start_media_monitor(client, stop_event)

    # Keep main thread alive until stop_event is set
    logger.info("Media Monitor running. Press Ctrl+C to exit.")
    try:
        while not stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
        stop_event.set()
        time.sleep(1)
        client.loop_stop()
        client.disconnect()
        sys.exit(0)
