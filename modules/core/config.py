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
        media_monitor: Enable media monitoring (default: False)
        game_monitor: Enable game monitoring (default: False)
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
import os
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
# Helper Functions
# ----------------------------


def is_interactive_environment() -> bool:
    """
    Determine if running in interactive environment.

    Returns True if:
    - stdin is a TTY (terminal)
    - DA_NON_INTERACTIVE env var is NOT set

    Returns False if:
    - stdin is not a TTY (pipe, file, CI/CD)
    - DA_NON_INTERACTIVE is explicitly set
    """
    import os

    # Explicit override takes precedence
    if os.getenv("DA_NON_INTERACTIVE"):
        return False

    # Check if stdin is connected to a terminal
    return sys.stdin.isatty()


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    """
    Prompt user for yes/no question with validation.

    Accepts: y, yes, n, no (case insensitive)
    Returns: boolean
    """
    default_str = "Y/n" if default else "y/N"

    while True:
        response = input(f"{prompt} [{default_str}]: ").strip().lower()

        if not response:  # User pressed Enter (use default)
            return default

        if response in ("y", "yes"):
            return True
        elif response in ("n", "no"):
            return False
        else:
            print("  Invalid input. Please enter 'y' for yes or 'n' for no.")


# ----------------------------
# Validation Functions
# ----------------------------


def validate_required_mqtt(
    broker: str, port: str, user: str, password: str
) -> tuple[bool, str]:
    """
    Validate required MQTT settings.

    Returns (is_valid, error_message).
    """
    if not broker or not broker.strip():
        return False, "MQTT broker cannot be empty"

    if not user or not user.strip():
        return False, "MQTT username cannot be empty"

    if not password:
        logger.warning("MQTT password is empty - ensure your broker allows this")

    try:
        port_int = int(port)
        if not (1 <= port_int <= 65535):
            return False, f"MQTT port must be between 1-65535, got {port}"
    except ValueError:
        return False, f"MQTT port must be a number, got '{port}'"

    return True, ""


# ----------------------------
# Interactive Configuration Creation
# ----------------------------


def create_config_interactive(config_path: Path) -> None:
    """
    Create configuration file interactively on first run.

    This function guides the user through setting up Desktop Agent,
    collecting required MQTT settings, optional module configurations,
    and automatically generating secure API keys when REST API is enabled.

    Falls back to non-interactive mode if not running in a terminal.

    Args:
        config_path: Path where config.ini should be created

    Behavior:
        - Creates parent directories if needed
        - Prompts for required settings (MQTT)
        - Prompts for optional modules
        - Generates secure API key using secrets.token_urlsafe(32) if REST enabled
        - Writes complete config.ini
        - Does NOT exit (unlike old behavior)

    Environment Variables (for automation/CI/CD only):
        DA_MQTT_BROKER: MQTT broker hostname
        DA_MQTT_PORT: MQTT broker port (default: 1883)
        DA_MQTT_USER: MQTT username
        DA_MQTT_PASS: MQTT password
        DA_DEVICE_NAME: Device name (default: hostname)
        DA_NON_INTERACTIVE: Set to skip prompts (uses env vars or defaults)
    """
    import os
    import secrets
    import socket

    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if running in interactive environment
    is_interactive = is_interactive_environment()

    try:
        if is_interactive:
            print("\n" + "=" * 70)
            print("Desktop Agent - First Run Configuration")
            print("=" * 70)
            print("\nWelcome! Let's configure Desktop Agent for your system.")
            print("You can press Enter to accept default values shown in [brackets].\n")

        # Get configuration values
        if is_interactive:
            device_name = (
                input(f"Device name [{socket.gethostname()}]: ").strip()
                or socket.gethostname()
            )

            print("\nMQTT Broker Settings (required):")
            mqtt_broker = ""
            while not mqtt_broker:
                mqtt_broker = input("  MQTT broker hostname/IP: ").strip()
                if not mqtt_broker:
                    print("  Error: MQTT broker is required!")

            mqtt_port = input("  MQTT port [1883]: ").strip() or "1883"

            mqtt_user = ""
            while not mqtt_user:
                mqtt_user = input("  MQTT username: ").strip()
                if not mqtt_user:
                    print("  Error: MQTT username is required!")

            mqtt_pass = ""
            while not mqtt_pass:
                mqtt_pass = input("  MQTT password: ").strip()
                if not mqtt_pass:
                    print("  Error: MQTT password is required!")

            # Validate MQTT settings
            valid, error = validate_required_mqtt(
                mqtt_broker, mqtt_port, mqtt_user, mqtt_pass
            )
            if not valid:
                print(f"  Error: {error}")
                print("  Please run Desktop Agent again to reconfigure.")
                sys.exit(1)

            print("\nOptional Modules:")
            api_enabled = prompt_yes_no("  Enable REST API?")
            commands_enabled = prompt_yes_no("  Enable remote commands?")
            media_enabled = prompt_yes_no("  Enable media monitoring?")
            game_enabled = prompt_yes_no("  Enable game monitoring?")
            updates_enabled = prompt_yes_no("  Enable automatic updates?")

            api_port = "5555"
            api_token = ""
            if api_enabled:
                api_port = input("  API port [5555]: ").strip() or "5555"
                # Generate secure API key automatically
                api_token = secrets.token_urlsafe(32)
                print("\n  " + "=" * 66)
                print("  SECURITY: Auto-generated API authentication token")
                print("  " + "=" * 66)
                print(f"  Token: {api_token}")
                print("  " + "=" * 66)
                print("  IMPORTANT: Save this token securely!")
                print("  You'll need it to authenticate REST API requests.")
                print("  This token will be saved to your config file.")
                print("  " + "=" * 66)
                input("\n  Press Enter to continue...")

            igdb_client_id = ""
            igdb_token = ""
            if game_enabled:
                print("\n  Game monitoring requires IGDB API credentials.")
                print("  Get them at: https://api-docs.igdb.com/#authentication")
                igdb_client_id = input("  IGDB Client ID: ").strip()
                igdb_token = input("  IGDB Access Token: ").strip()

        else:
            # Non-interactive mode: use environment variables or defaults
            device_name = os.getenv("DA_DEVICE_NAME", socket.gethostname())
            mqtt_broker = os.getenv("DA_MQTT_BROKER", "localhost")
            mqtt_port = os.getenv("DA_MQTT_PORT", "1883")
            mqtt_user = os.getenv("DA_MQTT_USER", "username")
            mqtt_pass = os.getenv("DA_MQTT_PASS", "password")
            api_enabled = False
            commands_enabled = False
            media_enabled = False
            game_enabled = False
            updates_enabled = False
            api_port = "5555"
            api_token = ""  # No API key in non-interactive mode (API disabled)
            igdb_client_id = ""
            igdb_token = ""

            logger.warning(
                "Non-interactive mode: Using environment variables or defaults"
            )
            logger.warning("Edit config.ini with real MQTT credentials before running!")

        # Write config file
        config_content = f"""; ================== DESKTOP AGENT CONFIG ==================
; Documentation: {REPO_URL}/wiki
; Generated on first run
; ==========================================================

[device]
name = {device_name}
interval = 10

[mqtt]
broker = {mqtt_broker}
port = {mqtt_port}
username = {mqtt_user}
password = {mqtt_pass}
max_connection_retries = 10
min_reconnect_delay = 1
max_reconnect_delay = 60
connection_timeout = 30

[modules]
api = {str(api_enabled).lower()}
commands = {str(commands_enabled).lower()}
media_monitor = {str(media_enabled).lower()}
game_monitor = {str(game_enabled).lower()}
updates = {str(updates_enabled).lower()}

[api]
port = {api_port}
auth_token = {api_token}

[updates]
interval = 3600
auto_install = false
channel = beta

[igdb]
client_id = {igdb_client_id}
token = {igdb_token}
"""

        config_path.write_text(config_content, encoding="utf-8")

        if is_interactive:
            print("\n" + "=" * 70)
            print(f"Configuration saved to: {config_path}")
            print("=" * 70)
            print("\nStarting Desktop Agent...\n")
        else:
            logger.info(f"Configuration created at {config_path}")

    except KeyboardInterrupt:
        print("\n\nSetup interrupted by user.")
        print("Config file not created. Please run again to complete setup.")
        sys.exit(1)
    except PermissionError:
        logger.error(f"Permission denied writing to: {config_path}")
        logger.error("Please check file permissions or run with appropriate privileges")
        sys.exit(1)
    except OSError as e:
        logger.error(f"Failed to write config file: {e}")
        sys.exit(1)


def load_config_with_first_run(config_path: Path) -> configparser.ConfigParser:
    """
    Load configuration file, creating it interactively if missing.

    This replaces the old behavior of exiting on missing config.
    Now we guide the user through setup and continue running.

    Args:
        config_path: Path to config.ini

    Returns:
        Loaded ConfigParser object
    """
    if not config_path.exists():
        create_config_interactive(config_path)

    config = configparser.ConfigParser()

    try:
        files_read = config.read(config_path)
        if not files_read:
            raise ValueError("Config file exists but couldn't be read")

        # Validate critical sections exist
        if not config.has_section("mqtt"):
            raise ValueError("Config file missing [mqtt] section")

        return config

    except (configparser.Error, ValueError) as e:
        logger.error(f"Configuration file is corrupt: {e}")
        logger.error(f"Location: {config_path}")

        # Prompt user for action if interactive
        if is_interactive_environment():
            print("\nYour configuration file is corrupt or incomplete.")
            print("Options:")
            print("  1. Backup current config and create new one")
            print("  2. Exit and manually fix the config")
            choice = input("\nChoose option [1/2]: ").strip()

            if choice == "1":
                backup_path = config_path.with_suffix(".ini.backup")
                config_path.rename(backup_path)
                logger.info(f"Backed up corrupt config to: {backup_path}")
                create_config_interactive(config_path)
                return load_config_with_first_run(config_path)
            else:
                sys.exit(1)
        else:
            # Non-interactive: can't prompt, must exit
            logger.error("Cannot repair config in non-interactive mode")
            sys.exit(1)


# ----------------------------
# Load configuration
# ----------------------------

config = load_config_with_first_run(CONFIG_PATH)


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
# Support environment variable override for testing/CI environments
# Check config first, then fall back to env var if empty
API_AUTH_TOKEN = config.get("api", "auth_token", fallback="").strip()
if not API_AUTH_TOKEN:
    API_AUTH_TOKEN = os.getenv("DA_API_AUTH_TOKEN", "")

# Enforce API authentication requirement
if API_MOD and not API_AUTH_TOKEN:
    logger.error("=" * 70)
    logger.error("ERROR: API is enabled but auth_token is NOT configured!")
    logger.error("Desktop Agent requires API authentication for security.")
    logger.error("Please add an auth_token to [api] section in config.ini")
    logger.error(
        'Generate token: python -c "import secrets; print(secrets.token_urlsafe(32))"'
    )
    logger.error("Or disable the API module: api = false")
    logger.error("=" * 70)
    sys.exit(1)  # Fail-fast on security issue


# ----------------------------
# Module Feature Flags
# ----------------------------

COMMANDS_MOD = config.getboolean("modules", "commands", fallback=False)
MEDIA_MONITOR = config.getboolean("modules", "media_monitor", fallback=False)
GAME_MONITOR = config.getboolean("modules", "game_monitor", fallback=False)


# ----------------------------
# Game Monitor Configuration
# ----------------------------

GAME_FILE = BASE_DIR / "data" / "game_monitor" / "current_game"
IGDB_CLIENT = config.get("igdb", "client_id", fallback="")
IGDB_TOKEN = config.get("igdb", "token", fallback="")

# Validate IGDB credentials if game monitor is enabled
if GAME_MONITOR and (not IGDB_CLIENT or not IGDB_TOKEN):
    logger.warning("=" * 70)
    logger.warning(
        "WARNING: Game monitor is enabled but IGDB credentials are not configured!"
    )
    logger.warning("Please add your IGDB client_id and token to config.ini")
    logger.warning("The game monitor will be disabled for this run.")
    logger.warning("=" * 70)
    GAME_MONITOR = False


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
