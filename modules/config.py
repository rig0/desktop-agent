import os
import sys
import configparser
from pathlib import Path


# ----------------------------
# Paths
# ----------------------------

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = os.path.join(BASE_DIR, "data", "config.ini")
VERSION_PATH = os.path.join(BASE_DIR, "VERSION")


# ----------------------------
# Load version
# ----------------------------

try:
    with open(VERSION_PATH, "r", encoding="utf-8") as f:
        VERSION = f.read().strip()
except FileNotFoundError:
    VERSION = "0.0.0"  # fallback if VERSION file is missing


# ----------------------------
# Create configuration (first run)
# ----------------------------
def create_default_config(config_path):
    config_content = """# ================== DESKTOP AGENT CONFIG ==================
    # These are the default values.
    # Intervals are in seconds.
    # Modules are disabled by default.
    # Documentation: https://github.com/rig0/hass-desktop-agent

    # If you enable the game agent, create an igdb.com account and fill your api credentials.
    # Read more https://api-docs.igdb.com/#authentication (Access token, not client secret!)

    [device]
    name = Device-Name
    interval = 10

    # Required!
    [mqtt]
    broker = homeassistant-ip
    port = 1883
    username = username
    password = password

    # Optional
    [modules]
    api = false
    commands = false
    media_agent = false
    game_agent = false
    updates = false

    # Module Options
    [api]
    port = 5555

    [updates]
    interval = 3600

    # Required for game_agent
    [igdb]
    client_id = your_igdb_client_id
    token = your_igdb_access_token
    """

    # Write to file
    with open(config_path, "w") as f:
        f.write(config_content)

    print(f"[Config] Default config created at: {config_path}.")

# ----------------------------
# Load configuration
# ----------------------------

config = configparser.ConfigParser()
if not config.read(CONFIG_PATH):
    print(f"\n[Config] Config file not found! \nCreating now...\n")

    create_default_config(CONFIG_PATH)

    print(f"\n[Config] Edit config with required info!: {CONFIG_PATH}\n")

    raise FileNotFoundError(f"[Config] Edit config with required info!: {CONFIG_PATH}")

DEVICE_NAME = config.get("device", "name")
PUBLISH_INT = config.getint("device", "interval", fallback=15)

MQTT_BROKER = config.get("mqtt", "broker")
MQTT_PORT = config.getint("mqtt", "port")
MQTT_USER = config.get("mqtt", "username")
MQTT_PASS = config.get("mqtt", "password")

API_MOD = config.getboolean("modules", "api", fallback=False)
API_PORT = config.getint("api", "port", fallback=5555)

UPDATES_MOD = config.getboolean("modules", "updates", fallback=False)
UPDATES_INT = config.getint("updates", "interval", fallback=3600)

MEDIA_AGENT = config.getboolean("modules", "media_agent", fallback=False)

COMMANDS_MOD = config.getboolean("modules", "commands", fallback=False)

GAME_AGENT = config.getboolean("modules", "game_agent", fallback=False)
GAME_FILE = os.path.join(BASE_DIR, "data", "current_game.txt")
IGDB_CLIENT = config.get("igdb", "client_id")
IGDB_TOKEN = config.get("igdb", "token")


# ----------------------------
# Device identifiers and topics
# ----------------------------

device_id = DEVICE_NAME.lower().replace(" ", "_")
base_topic = f"desktop/{device_id}"
discovery_prefix = "homeassistant"


# ----------------------------
# Device Info
# ----------------------------

device_info = {
    "identifiers": [device_id],
    "name": DEVICE_NAME,
    "manufacturer": "Rigo Sotomayor",
    "model": "Desktop Agent",
    "sw_version": VERSION,
    "configuration_url": "https://github.com/rig0/hass-desktop-agent",
}
