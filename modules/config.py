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
# Load configuration
# ----------------------------
config = configparser.ConfigParser()
if not config.read(CONFIG_PATH):
    raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")

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

LUTRIS_AGENT = config.getboolean("modules", "lutris_agent", fallback=False)
IGDB_CLIENT = config.getboolean("igdb", "client_id")
IGDB_TOKEN = config.getint("igdb", "token")

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
