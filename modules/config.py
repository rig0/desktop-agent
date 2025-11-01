import sys, shutil, configparser
from pathlib import Path


# ----------------------------
# Paths
# ----------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "data" / "config.ini"
VERSION_PATH = BASE_DIR / "VERSION"


# ----------------------------
# Load version
# ----------------------------

try:
    with VERSION_PATH.open("r", encoding="utf-8") as f:
        VERSION = f.read().strip()
except FileNotFoundError:
    VERSION = "0.0.0"  # fallback if VERSION file is missing


# ----------------------------
# Repository Information
# ----------------------------

REPO_OWNER = "rig0"
REPO_NAME = "desktop-agent"
REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
REPO_WIKI_URL = f"{REPO_URL}/wiki/"


# ----------------------------
# Create configuration (first run)
# ----------------------------
def create_config(config_path: Path): 
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        print(f"\n[Config] Config file not found! Creating now...")
        
        src = BASE_DIR / "resources" / "config_example.ini"
        shutil.copy(src, config_path)

        print(f"\n[Config] Created default config at {config_path}")
        print(f"\n[Config] Edit config.ini with required info! Exiting...\n")   
        exit(1)    


# ----------------------------
# Load configuration
# ----------------------------

config = configparser.ConfigParser()
if not config.read(CONFIG_PATH):
    create_config(CONFIG_PATH)


# ----------------------------
# Configuration values
# ----------------------------

DEVICE_NAME = config.get("device", "name")
PUBLISH_INT = config.getint("device", "interval", fallback=15)

MQTT_BROKER = config.get("mqtt", "broker")
MQTT_PORT = config.getint("mqtt", "port")
MQTT_USER = config.get("mqtt", "username")
MQTT_PASS = config.get("mqtt", "password")

API_MOD = config.getboolean("modules", "api", fallback=False)
API_PORT = config.getint("api", "port", fallback=5555)

COMMANDS_MOD = config.getboolean("modules", "commands", fallback=False)
MEDIA_AGENT = config.getboolean("modules", "media_agent", fallback=False)

GAME_AGENT = config.getboolean("modules", "game_agent", fallback=False)
GAME_FILE = BASE_DIR / "data" / "game_agent" / "current_game"

IGDB_CLIENT = config.get("igdb", "client_id")
IGDB_TOKEN = config.get("igdb", "token")

# Validate IGDB credentials if game agent is enabled
if GAME_AGENT and (not IGDB_CLIENT or not IGDB_TOKEN):
    print("[Config] WARNING: Game agent is enabled but IGDB credentials are not configured!")
    print("[Config] Please add your IGDB client_id and token to config.ini")
    print("[Config] The game agent will be disabled for this run.")
    GAME_AGENT = False

UPDATES_MOD = config.getboolean("modules", "updates", fallback=False)
UPDATES_INT = config.getint("updates", "interval", fallback=3600)
UPDATES_AUTO = config.getboolean("updates", "auto_install", fallback=False)
UPDATES_CH = config.get("updates", "channel", fallback="stable")

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
    "configuration_url": REPO_URL,
}
