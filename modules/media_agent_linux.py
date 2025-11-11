# Standard library imports
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

# Third-party imports
import paho.mqtt.client as mqtt
import requests
from pydbus import SessionBus

# Local imports
from modules.config import (
    DEVICE_NAME,
    base_topic,
    device_id,
    device_info,
    discovery_prefix,
)

# Configure logger
logger = logging.getLogger(__name__)


# ----------------------------
# Linux Media Agent (MPRIS/D-Bus)
# ----------------------------

def get_media_info():
    try:
        bus = SessionBus()
        dbus = bus.get("org.freedesktop.DBus", "/org/freedesktop/DBus")
        players = [name for name in dbus.ListNames() if name.startswith("org.mpris.MediaPlayer2.")]
        if not players:
            return None

        selected_player = None
        # Find a player that is currently playing
        for name in players:
            player = bus.get(name, "/org/mpris/MediaPlayer2")
            if getattr(player, "PlaybackStatus", "").lower() == "playing":
                selected_player = player
                break

        # If none are playing, fallback to first available
        if not selected_player:
            selected_player = bus.get(players[0], "/org/mpris/MediaPlayer2")

        metadata = selected_player.Metadata
        status = selected_player.PlaybackStatus

        title = metadata.get("xesam:title", "")
        artist = ", ".join(metadata.get("xesam:artist", [])) if metadata.get("xesam:artist") else ""
        album = metadata.get("xesam:album", "")
        is_playing = status.lower() == "playing"

        thumbnail_bytes = None
        art_url = metadata.get("mpris:artUrl")
        if art_url:
            try:
                if art_url.startswith("file://"):
                    path = art_url[7:]
                    if os.path.exists(path):
                        with open(path, "rb") as f:
                            thumbnail_bytes = f.read()
                else:
                    resp = requests.get(art_url, timeout=5)
                    if resp.ok:
                        thumbnail_bytes = resp.content
            except (IOError, OSError) as e:
                logger.error(f"Failed to read artwork from file: {e}")
            except requests.RequestException as e:
                logger.error(f"Failed to fetch artwork from URL: {e}")
            except Exception as e:
                logger.error(f"Unexpected error fetching artwork: {e}", exc_info=True)

        return {
            "title": title,
            "artist": artist,
            "album": album,
            "is_playing": is_playing,
            "playback_status": status,
            "thumbnail_bytes": thumbnail_bytes
        }

    except Exception as e:
        logger.error(f"Error getting media info: {e}", exc_info=True)
        return None


def start_media_agent(client: mqtt.Client, stop_event):
    # Starts the media polling thread and publishes discovery.
    def media_poller():
        logger.info("Media Agent poller thread started")
        last_attrs = None
        last_image = None
        BASE_DIR = Path(__file__).parent.parent
        placeholder_path = BASE_DIR / "resources" / "media_thumb.png"
        placeholder_path_custom = BASE_DIR / "data" / "media_agent" / "media_thumb.png"

        try:
            while not stop_event.is_set():
                try:
                    info = get_media_info()
                    if info:
                        state = "playing" if info["is_playing"] else "paused" if info["playback_status"].lower() == "paused" else "idle"
                        attrs = {
                            "title": info["title"],
                            "artist": info["artist"],
                            "album": info["album"],
                            "status": state
                        }

                        # Publish state
                        client.publish(f"{base_topic}/media/state", state, retain=True)

                        # Publish attributes if changed
                        if attrs != last_attrs:
                            client.publish(f"{base_topic}/media/attrs", json.dumps(attrs), retain=False)
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
                                    logger.error(f"Failed to load default placeholder thumbnail: {e}")
                                    thumbnail_bytes = None

                        # Only publish if image changed
                        if thumbnail_bytes and thumbnail_bytes != last_image:
                            client.publish(f"{base_topic}/media/thumbnail", thumbnail_bytes, retain=True)
                            last_image = thumbnail_bytes

                except Exception as e:
                    logger.error(f"Error in media poller: {e}", exc_info=True)

                # Sleep but allow interruption
                stop_event.wait(5)
        except Exception as e:
            logger.critical(f"Fatal error in Media Agent poller thread: {e}", exc_info=True)
        finally:
            logger.info("Media Agent poller thread stopped")

    def publish_discovery():
        try:
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

            camera_payload = {
                "platform": "mqtt",
                "name": f"{DEVICE_NAME} Media",
                "unique_id": f"{device_id}_media",
                "device": device_info,
                "availability_topic": f"{base_topic}/availability",
                "topic": f"{base_topic}/media/thumbnail",
                "icon": "mdi:music"
            }

            topic = f"{discovery_prefix}/camera/{device_id}_media/config"
            client.publish(topic, json.dumps(camera_payload), retain=True)
            logger.debug("Published discovery for media camera")
            logger.info("Published discovery for media agent entities")
        except Exception as e:
            logger.error(f"Error publishing media agent discovery: {e}", exc_info=True)

    publish_discovery()
    threading.Thread(target=media_poller, name="MediaAgent-Poller", daemon=True).start()
