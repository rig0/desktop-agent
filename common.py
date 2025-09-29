import os
import sys
import configparser

# ----------------------------
# Base paths
# ----------------------------
BASE_DIR = os.path.dirname(
    sys.executable if getattr(sys, "frozen", False) else __file__
)
CONFIG_PATH = os.path.join(BASE_DIR, "config", "config.ini")
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

DEVICE_NAME = config["device"]["name"]

MQTT_BROKER = config["mqtt"]["broker"]
MQTT_PORT = int(config["mqtt"]["port"])
MQTT_USER = config["mqtt"]["username"]
MQTT_PASS = config["mqtt"]["password"]

API_PORT = int(config["api"]["port"])
PUBLISH_INTERVAL = int(config["device"].get("interval", 30))  # seconds

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
