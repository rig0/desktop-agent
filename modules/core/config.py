"""Configuration management for Desktop Agent.

This module provides centralized configuration management for the entire Desktop Agent
application. It handles loading settings from config.ini, validating required values,
setting up paths, and providing configuration constants to all other modules.

The configuration system follows these principles:
- Single source of truth for all application settings
- Fail-fast on critical configuration errors (missing IGDB credentials when needed)
- Sensible defaults for optional settings
- Clear warnings for security issues (missing API auth token)
- Platform-independent path handling using pathlib

Configuration Structure:
    [device]
        name: Human-readable device name (e.g., "Gaming PC")
        interval: Publishing interval in seconds for system metrics

    [mqtt]
        broker: MQTT broker hostname or IP address
        port: MQTT broker port (typically 1883)
        username: MQTT authentication username
        password: MQTT authentication password
        max_connection_retries: Maximum connection attempts before failure
        min_reconnect_delay: Initial reconnection delay in seconds
        max_reconnect_delay: Maximum reconnection delay in seconds
        connection_timeout: Timeout for initial connection in seconds

    [modules]
        api: Enable REST API server (default: False)
        commands: Enable MQTT command execution (default: False)
        media_agent: Enable media monitoring (default: False)
        game_agent: Enable game monitoring (default: False)
        updates: Enable automatic update checks (default: False)

    [api]
        port: API server port (default: 5555)
        auth_token: Bearer token for API authentication

    [igdb]
        client_id: IGDB API client ID for game metadata
        token: IGDB API authentication token

    [updates]
        interval: Update check interval in seconds (default: 3600)
        auto_install: Automatically install updates (default: False)
        channel: Update channel (stable or beta, default: beta)

Usage:
    from modules.core.config import MQTT_BROKER, MQTT_PORT, device_id

    # Connect to broker
    client.connect(MQTT_BROKER, MQTT_PORT)

    # Use device identifiers
    topic = f"desktop/{device_id}/status"

Example:
    >>> from modules.core.config import DEVICE_NAME, VERSION
    >>> print(f"{DEVICE_NAME} v{VERSION}")
    'Gaming PC v0.10.5'
"""

# Standard library imports
import configparser
import logging
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

# Configure logger for config module
logger = logging.getLogger(__name__)


# ----------------------------
# Paths
# ----------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent
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
    logger.warning(f"VERSION file not found at {VERSION_PATH}, using fallback: {VERSION}")


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


def create_config(config_path: Path) -> None:
    """
    Create default configuration file from template.

    On first run, copies the example configuration file from resources/
    to the data/ directory. This provides users with a template containing
    all available configuration options with explanatory comments.

    Args:
        config_path: Path where config.ini should be created

    Behavior:
        - Creates parent directories if they don't exist
        - Copies config_example.ini to config.ini
        - Prints instructions for user to edit the file
        - Exits the application to force user configuration

    Exit Codes:
        1: Configuration file created, user must edit before running

    Example:
        This function is called automatically when config.ini is missing:

        [Config] Config file not found! Creating now...
        [Config] Created default config at /path/to/data/config.ini
        [Config] Edit config.ini with required info! Exiting...
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        print("\n[Config] Config file not found! Creating now...")

        src = BASE_DIR / "resources" / "config_example.ini"
        shutil.copy(src, config_path)

        print(f"\n[Config] Created default config at {config_path}")
        print("\n[Config] Edit config.ini with required info! Exiting...\n")
        sys.exit(1)


# ----------------------------
# Load configuration
# ----------------------------

config = configparser.ConfigParser()
if not config.read(CONFIG_PATH):
    create_config(CONFIG_PATH)


# ----------------------------
# Device Configuration
# ----------------------------

DEVICE_NAME = config.get("device", "name")
PUBLISH_INT = config.getint("device", "interval", fallback=15)


# ----------------------------
# MQTT Configuration
# ----------------------------

MQTT_BROKER = config.get("mqtt", "broker")
MQTT_PORT = config.getint("mqtt", "port")
MQTT_USER = config.get("mqtt", "username")
MQTT_PASS = config.get("mqtt", "password")
MQTT_MAX_RETRIES = config.getint("mqtt", "max_connection_retries", fallback=10)
MQTT_MIN_RECONNECT_DELAY = config.getint("mqtt", "min_reconnect_delay", fallback=1)
MQTT_MAX_RECONNECT_DELAY = config.getint("mqtt", "max_reconnect_delay", fallback=60)
MQTT_CONNECTION_TIMEOUT = config.getint("mqtt", "connection_timeout", fallback=30)


# ----------------------------
# API Configuration
# ----------------------------

API_MOD = config.getboolean("modules", "api", fallback=False)
API_PORT = config.getint("api", "port", fallback=5555)
API_AUTH_TOKEN = config.get("api", "auth_token", fallback="").strip()

# Validate API authentication configuration
if API_MOD and not API_AUTH_TOKEN:
    logger.warning("=" * 70)
    logger.warning("WARNING: API is enabled but auth_token is NOT configured!")
    logger.warning("Your API endpoints are accessible without authentication.")
    logger.warning("This is a SECURITY RISK if your system is exposed to network.")
    logger.warning("Please add an auth_token to [api] section in config.ini")
    logger.warning(
        'Generate token: python -c "import secrets; print(secrets.token_urlsafe(32))"'
    )
    logger.warning("=" * 70)


# ----------------------------
# Module Feature Flags
# ----------------------------

COMMANDS_MOD = config.getboolean("modules", "commands", fallback=False)
MEDIA_AGENT = config.getboolean("modules", "media_agent", fallback=False)
GAME_AGENT = config.getboolean("modules", "game_agent", fallback=False)


# ----------------------------
# Game Agent Configuration
# ----------------------------

GAME_FILE = BASE_DIR / "data" / "game_agent" / "current_game"
IGDB_CLIENT = config.get("igdb", "client_id", fallback="")
IGDB_TOKEN = config.get("igdb", "token", fallback="")

# Validate IGDB credentials if game agent is enabled
if GAME_AGENT and (not IGDB_CLIENT or not IGDB_TOKEN):
    logger.warning("=" * 70)
    logger.warning(
        "WARNING: Game agent is enabled but IGDB credentials are not configured!"
    )
    logger.warning("Please add your IGDB client_id and token to config.ini")
    logger.warning("The game agent will be disabled for this run.")
    logger.warning("=" * 70)
    GAME_AGENT = False


# ----------------------------
# Update Manager Configuration
# ----------------------------

UPDATES_MOD = config.getboolean("modules", "updates", fallback=False)
UPDATES_INT = config.getint("updates", "interval", fallback=3600)
UPDATES_AUTO = config.getboolean("updates", "auto_install", fallback=False)
UPDATES_CH = config.get("updates", "channel", fallback="beta")

# Force 'beta' if set to 'stable' until there's an actual stable release
if UPDATES_CH == "stable":
    UPDATES_CH = "beta"
    logger.info("Update channel forced to 'beta' (stable releases not yet available)")


# ----------------------------
# Device identifiers and topics
# ----------------------------

device_id = DEVICE_NAME.lower().replace(" ", "_")
base_topic = f"desktop/{device_id}"
discovery_prefix = "homeassistant"


# ----------------------------
# Device Info Dictionary
# ----------------------------

device_info: Dict[str, Any] = {
    "identifiers": [device_id],
    "name": DEVICE_NAME,
    "manufacturer": "Rigo Sotomayor",
    "model": "Desktop Agent",
    "sw_version": VERSION,
    "configuration_url": REPO_URL,
}
