import os, json, time, threading
import paho.mqtt.client as mqtt
# Attempt relative import for use as a module within a package structure
try:
    from .igdb import IGDBClient
    from .config import IGDB_CLIENT, IGDB_TOKEN, MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS, DEVICE_NAME, \
                device_id, base_topic, discovery_prefix, device_info
# Fall back to direct import which assumes the script is being ran standalone
except ImportError:
    from igdb import IGDBClient
    from config import IGDB_CLIENT, IGDB_TOKEN, MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS, DEVICE_NAME, \
                device_id, base_topic, discovery_prefix, device_info


# ----------------------------
# Game Agent
# ----------------------------

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {str(rc)}")

def get_game_info(game):
    igdb = IGDBClient(IGDB_CLIENT, IGDB_TOKEN)
    game_info = igdb.search_game(game)
    return game_info

def get_game_artwork(img_dir, img_url):
    img_bytes = None
    try:
        if img_dir and os.path.exists(img_dir):
            with open(img_dir, "rb") as f:
                img_bytes = f.read()

        elif img_url:
            resp = requests.get(img_url, timeout=5)
            if resp.ok:
                img_bytes = resp.content

    except Exception as e:
        print(f"Failed to fetch cover: {e}")
        
    return img_bytes

def get_game_attrs(game_info):
    # Extracting the cover URL and replacing 't_thumb' with 't_cover_big'
    cover_url = game_info["_raw"].get("cover", {}).get("url", "")
    cover_full_url = "https:" + cover_url.replace("t_thumb", "t_cover_big") if cover_url.startswith("//") else cover_url

    # Attempt to extract last artwork's URL; fall back to first screenshot if necessary
    artworks = game_info["_raw"].get("artworks", [])
    screenshots = game_info["_raw"].get("screenshots", [])
    
    # If there are artworks, use the last one with 't_original'; otherwise, check for screenshots
    if artworks:
        artwork_url = artworks[-1].get("url", "")
        artwork_full_url = "https:" + artwork_url.replace("t_thumb", "t_original") if artwork_url.startswith("//") else artwork_url
    elif screenshots:
        # If there's no artwork but there are screenshots, use the first screenshot with 't_original'
        screenshot_url = screenshots[0].get("url", "")
        artwork_full_url = "https:" + screenshot_url.replace("t_thumb", "t_original") if screenshot_url.startswith("//") else screenshot_url
    else:
        artwork_full_url = None  # No artwork or screenshot available

    # Get cached images 
    cover_local = game_info['cover']
    artwork_local = game_info['artwork']

    # Get images in bytes. Try cache, if not fetch from url
    cover_bytes = get_game_artwork(cover_local, cover_full_url)
    artwork_bytes = get_game_artwork(artwork_local, artwork_full_url)

    attrs = {
        "name": game_info.get("name", "Unknown Game"),
        "summary": game_info.get("summary", "No summary available."),
        "release_date": game_info.get("release_date", "Not available"),
        "genres": ', '.join(game_info.get("genres", [])),
        "developers": ', '.join(game_info.get("developers", [])),
        "platforms": ', '.join(game_info.get("platforms", [])),
        "total_rating": round(game_info.get("total_rating", 0), 2),
        "cover_url": cover_full_url or "Cover image not available",
        "artwork_url": artwork_full_url or "Artwork not available",
        "url": game_info.get("url", "")
    }

    images = {
        "cover": cover_bytes,
        "artwork": artwork_bytes
    }

    return attrs, images

def start_game_agent(client: mqtt.Client, game_name_file_path):
    def game_poller():
        print("Game poller thread started")
        last_attrs = None
        last_known_game_name = None
        last_cover = None
        last_artwork = None

        while True:
            try:
                # Read game name from file
                try:
                    with open(game_name_file_path, 'r') as f:
                        game_name = f.readline().strip()
                except FileNotFoundError:
                    game_name = None

                if game_name and game_name != last_known_game_name:
                    game_info = get_game_info(game_name)
                    attrs, images = get_game_attrs(game_info)
                    state = "playing"

                    # Publish state
                    client.publish(f"{base_topic}/game/state", state, retain=True)

                    # Publish attributes if changed
                    if attrs != last_attrs:
                        client.publish(f"{base_topic}/game/attrs", json.dumps(attrs), retain=True)
                        last_attrs = attrs
                    
                    # Publish cover image if changed
                    cover_bytes = images["cover"]
                    if cover_bytes and cover_bytes != last_cover:
                        client.publish(f"{base_topic}/game/cover", cover_bytes, retain=True)
                        last_cover = cover_bytes

                    # Publish artwork image if changed
                    artwork_bytes = images["artwork"]
                    if artwork_bytes and artwork_bytes != last_artwork:
                        client.publish(f"{base_topic}/game/artwork", artwork_bytes, retain=True)
                        last_artwork = artwork_bytes

                    last_known_game_name = game_name

                elif not game_name:
                    # If GAME_NAME is empty, the game is no longer running.
                    if last_known_game_name is not None:
                        client.publish(f"{base_topic}/game/state", "idle", retain=True)
                        last_known_game_name = None
            
            except Exception as e:
                print("Game poller error:", e)

            # Check for new game every 5 seconds
            time.sleep(5)

    def publish_discovery():
        sensor_payload = {
            "name": f"{DEVICE_NAME} Game Status",
            "state_topic": f"{base_topic}/game/state",
            "json_attributes_topic": f"{base_topic}/game/attrs",
            "icon": "mdi:gamepad-variant",
            "unique_id": f"{device_id}_game_status",
            "device": device_info,
            "availability_topic": f"{base_topic}/availability"
        }

        topic = f"{discovery_prefix}/sensor/{device_id}/game_status/config"
        client.publish(topic, json.dumps(sensor_payload), retain=True)
        print("Published discovery for game status")

        cover_payload = {
            "platform": "mqtt",
            "name": f"{DEVICE_NAME} Game Cover",
            "unique_id": f"{device_id}_game_cover",
            "device": device_info,
            "availability_topic": f"{base_topic}/availability",
            "topic": f"{base_topic}/game/cover",
            "icon": "mdi:gamepad-variant"
        }

        topic = f"{discovery_prefix}/camera/{device_id}_game_cover/config"
        client.publish(topic, json.dumps(cover_payload), retain=True)
        print("Published discovery for game cover")

        artwork_payload = {
            "platform": "mqtt",
            "name": f"{DEVICE_NAME} Game Art",
            "unique_id": f"{device_id}_game_artwork",
            "device": device_info,
            "availability_topic": f"{base_topic}/availability",
            "topic": f"{base_topic}/game/artwork",
            "icon": "mdi:gamepad-variant"
        }

        topic = f"{discovery_prefix}/camera/{device_id}_game_artwork/config"
        client.publish(topic, json.dumps(artwork_payload), retain=True)
        print("Published discovery for game artwork") 

    publish_discovery()
    threading.Thread(target=game_poller, daemon=True).start()

# Setup MQTT client and start the agent
if __name__ == "__main__":
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    start_game_agent(client)
    while True:
        time.sleep(1)
