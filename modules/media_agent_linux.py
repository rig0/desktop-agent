import os, sys, time, json, threading, requests
from pydbus import SessionBus
from pathlib import Path
from modules.config import DEVICE_NAME, device_id, base_topic, discovery_prefix, device_info
import paho.mqtt.client as mqtt


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
            except Exception as e:
                print("Failed to fetch artwork:", e)

        return {
            "title": title,
            "artist": artist,
            "album": album,
            "is_playing": is_playing,
            "playback_status": status,
            "thumbnail_bytes": thumbnail_bytes
        }

    except Exception as e:
        print("Error getting media info:", e)
        return None


def start_media_agent(client: mqtt.Client):
    # Starts the media polling thread and publishes discovery.
    def media_poller():
        print("Media poller thread started")
        last_attrs = None
        last_image = None
        BASE_DIR = Path(__file__).parent.parent
        placeholder_path = BASE_DIR / "data" / "media_thumb.png"

        while True:
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
                        client.publish(f"{base_topic}/media/attrs", json.dumps(attrs), retain=True)
                        last_attrs = attrs

                    # Thumbnail or placeholder
                    thumbnail_bytes = info.get("thumbnail_bytes")
                    if not thumbnail_bytes and placeholder_path.exists():
                        try:
                            with open(placeholder_path, "rb") as f:
                                thumbnail_bytes = f.read()
                        except Exception as e:
                            print("Failed to load placeholder:", e)
                            thumbnail_bytes = None

                    # Only publish if image changed
                    if thumbnail_bytes and thumbnail_bytes != last_image:
                        client.publish(f"{base_topic}/media/thumbnail", thumbnail_bytes, retain=True)
                        last_image = thumbnail_bytes

            except Exception as e:
                print("Media poller error:", e)

            time.sleep(5)

    def publish_discovery():
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
        print("Published discovery for media status")

        camera_payload = {
            "platform": "mqtt",
            "name": f"{DEVICE_NAME} Media",
            "unique_id": f"{device_id}_media",
            "device": device_info,
            "availability_topic": f"{base_topic}/availability",
            "topic": f"{base_topic}/media/thumbnail",
            "json_attributes_topic": f"{base_topic}/media/attrs",
            "icon": "mdi:music"
        }

        topic = f"{discovery_prefix}/camera/{device_id}_media/config"
        client.publish(topic, json.dumps(camera_payload), retain=True)
        print("Published discovery for media camera")

    publish_discovery()
    threading.Thread(target=media_poller, daemon=True).start()
