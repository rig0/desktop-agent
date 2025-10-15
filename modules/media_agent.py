import os, sys, time, json, asyncio, threading
from pathlib import Path
from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
import paho.mqtt.client as mqtt
from modules.config import MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS, PUBLISH_INT, \
                    DEVICE_NAME, device_id, base_topic, discovery_prefix, device_info

# ----------------------------
# Media (SMTC) helpers
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
            print("Failed to read thumbnail:", e)

    playback = current.get_playback_info()
    status = int(playback.playback_status)
    is_playing = status == 4

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "is_playing": is_playing,
        "playback_status": status,
        "thumbnail_bytes": thumbnail_bytes
    }


def get_media_info():
    try:
        return asyncio.run(_get_media_info_async())
    except Exception as e:
        print("Error getting media info:", e)
        return None


def start_media_agent(client: mqtt.Client):
    # Starts the media polling thread and publishes discovery.
    def media_poller():
        last_attrs = None
        last_image = None
        BASE_DIR = Path(__file__).parent.parent
        placeholder_path = BASE_DIR / "config" / "media_thumb.png"

        while True:
            try:
                info = get_media_info()
                if info:
                    state = "playing" if info["is_playing"] else "paused" if info["playback_status"] == 5 else "idle"
                    attrs = {
                        "title": info["title"],
                        "artist": info["artist"],
                        "album": info["album"],
                        "status": state
                    }

                    client.publish(f"{base_topic}/media/state", state, retain=True)

                    if attrs != last_attrs:
                        client.publish(f"{base_topic}/media/attrs", json.dumps(attrs), retain=True)
                        last_attrs = attrs

                    thumbnail_bytes = info.get("thumbnail_bytes")
                    if not thumbnail_bytes:
                        try:
                            with open(placeholder_path, "rb") as f:
                                thumbnail_bytes = f.read()
                        except Exception as e:
                            print("Failed to load placeholder:", e)
                            thumbnail_bytes = None

                    if thumbnail_bytes and thumbnail_bytes != last_image:
                        client.publish(f"{base_topic}/media/thumbnail", thumbnail_bytes, retain=True)
                        last_image = thumbnail_bytes

            except Exception as e:
                print("Media poller error:", e)

            time.sleep(5)

    def publish_discovery():
        # Simple media state sensor
        sensor_payload = {
            "name": "Media Status",
            "state_topic": f"{base_topic}/media/state",
            "icon": "mdi:multimedia",
            "unique_id": f"{device_id}_media_status",
            "device": device_info,
            "availability_topic": f"{base_topic}/availability"
        }

        topic = f"{discovery_prefix}/sensor/{device_id}/media_status/config"
        client.publish(topic, json.dumps(sensor_payload), retain=True)
        print("Published discovery for media status")

        # Camera-style media thumbnail
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

def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT broker with result code {rc}")
    publish_discovery()
    
if __name__ == "__main__":
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    start_media_agent(client)