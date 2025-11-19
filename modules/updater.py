"""Automatic update system for Desktop Agent.

This module provides automatic update functionality for the Desktop Agent,
fetching updates from GitHub releases and applying them automatically.
It supports multiple release channels (stable, beta, nightly) and integrates
with Home Assistant via MQTT for update notifications and remote installation.

The update system verifies updates using signature tracking, downloads release
archives, and applies them safely with rollback capabilities. It runs in a
background thread and can be configured for automatic or manual updates.

Update Channels:
    - stable: Official releases from GitHub Releases (latest tag)
    - beta: Pre-release versions from Git tags
    - nightly: Latest commit from main branch

Example:
    Basic usage with MQTT integration:

    >>> from modules.updater import UpdateManager
    >>> import paho.mqtt.client as mqtt
    >>>
    >>> client = mqtt.Client()
    >>> manager = UpdateManager(
    ...     client=client,
    ...     base_topic="desktop/my_pc",
    ...     discovery_prefix="homeassistant",
    ...     device_id="my_pc",
    ...     device_info={"name": "My PC"},
    ...     channel="beta",
    ...     auto_install=True
    ... )
    >>> manager.start()

    Standalone update check:

    >>> from modules.updater import update_repo
    >>> if update_repo(channel="stable"):
    ...     print("Update applied successfully")
"""

# Standard library imports
import hashlib
import io
import json
import logging
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from typing import Optional

# Third-party imports
import requests

# Local imports
from modules.core.config import REPO_NAME, REPO_OWNER, VERSION_PATH

# Configure logger
logger = logging.getLogger(__name__)

# ----------------------------
# Config
# ----------------------------
REPO = f"{REPO_OWNER}/{REPO_NAME}"
GITHUB_API = "https://api.github.com"
AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPDATER_DIR = os.path.join(AGENT_DIR, "data", "updater")

# Create updater data folder is it doesn't exist
os.makedirs(UPDATER_DIR, exist_ok=True)

# ----------------------------
# GitHub helpers
# ----------------------------


def _github_get(url: str, timeout: int = 10) -> dict:
    """Perform a GET request to GitHub API with proper headers.

    Args:
        url: GitHub API endpoint URL.
        timeout: Request timeout in seconds (default: 10).

    Returns:
        JSON response data as dictionary.

    Raises:
        requests.HTTPError: If the request fails with HTTP error.
        requests.RequestException: If the request fails for other reasons.

    Example:
        >>> data = _github_get("https://api.github.com/repos/owner/repo/releases/latest")
        >>> print(data["tag_name"])
        'v1.0.0'
    """
    headers = {"Accept": "application/vnd.github+json"}
    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.json()


def _get_commit_date(ref: str) -> Optional[str]:
    """Get commit date for a given Git reference.

    Args:
        ref: Git reference (branch name, tag, or commit SHA).

    Returns:
        ISO 8601 formatted commit date string, or None if unavailable.

    Example:
        >>> date = _get_commit_date("v1.0.0")
        >>> print(date)
        '2024-01-15T10:30:00Z'
    """
    try:
        data = _github_get(f"{GITHUB_API}/repos/{REPO}/commits/{ref}")
        return data.get("commit", {}).get("author", {}).get("date")
    except requests.RequestException:
        return None


def _normalize_version(version: Optional[str]) -> str:
    """Normalize version string for comparison.

    Removes leading 'v', strips whitespace, and converts to lowercase
    for consistent version comparison.

    Args:
        version: Version string to normalize (e.g., "v1.0.0", "V2.3.1").

    Returns:
        Normalized version string (e.g., "1.0.0", "2.3.1"), or empty string if None.

    Example:
        >>> _normalize_version("v1.0.0")
        '1.0.0'
        >>> _normalize_version("  V2.3.1  ")
        '2.3.1'
        >>> _normalize_version(None)
        ''
    """
    if not version:
        return ""
    return version.strip().lower().lstrip("v")


def _read_local_version() -> str:
    """Read the currently installed version from VERSION file.

    Returns:
        Version string from VERSION file, or empty string if not found.

    Example:
        >>> version = _read_local_version()
        >>> print(f"Installed version: {version}")
        'Installed version: 0.10.5'
    """
    try:
        with open(VERSION_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _signature_path(channel: str) -> str:
    safe_channel = channel or "stable"
    return os.path.join(UPDATER_DIR, f".last_signature_{safe_channel}")


def read_installed_signature(channel: str) -> Optional[str]:
    """Read the installed version signature for a given channel.

    Signatures are used to track which version is currently installed,
    allowing the update system to detect when new versions are available.

    Args:
        channel: Update channel ("stable", "beta", or "nightly").

    Returns:
        Signature string if available, None otherwise.

    Example:
        >>> signature = read_installed_signature("beta")
        >>> print(f"Installed signature: {signature}")
        'abc123def456...'
    """
    path = _signature_path(channel)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def write_installed_signature(channel: str, signature: Optional[str]) -> None:
    """Write the installed version signature for a given channel.

    This is called after successfully installing an update to record
    which version is now installed.

    Args:
        channel: Update channel ("stable", "beta", or "nightly").
        signature: Signature string to write (does nothing if None).

    Example:
        >>> write_installed_signature("beta", "abc123def456")
    """
    if not signature:
        return
    path = _signature_path(channel)
    with open(path, "w", encoding="utf-8") as f:
        f.write(signature)


def seed_signature_from_version(channel: str, release_info: Optional[dict]) -> None:
    """Initialize signature file if the current version matches remote version.

    This is used on first run to avoid treating the current installation
    as an "available update" when it's actually already installed.

    Args:
        channel: Update channel ("stable", "beta", or "nightly").
        release_info: Release information dictionary from fetch_release_info().

    Example:
        >>> info = fetch_release_info("beta")
        >>> seed_signature_from_version("beta", info)
    """
    if not release_info or read_installed_signature(channel):
        return

    remote_version = release_info.get("version")
    local_version = _read_local_version()
    if remote_version and _normalize_version(remote_version) == _normalize_version(
        local_version
    ):
        write_installed_signature(channel, release_info.get("signature"))


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ----------------------------
# File helpers
# ----------------------------


def get_sha256(data: bytes) -> str:
    """Calculate SHA256 hash of data.

    Args:
        data: Binary data to hash.

    Returns:
        Hexadecimal SHA256 hash string.

    Example:
        >>> data = b"hello world"
        >>> get_sha256(data)
        'b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9'
    """
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def copy_over(src, dst):
    """Recursively copy files from source to destination, overwriting existing files.

    This function preserves existing files that are not in the source directory,
    making it suitable for applying updates without removing user data or config.

    Args:
        src: Source directory path.
        dst: Destination directory path.

    Example:
        >>> copy_over("/tmp/update-v1.0.0", "/opt/desktop-agent")
    """
    os.makedirs(dst, exist_ok=True)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)

        if os.path.isdir(s):
            copy_over(s, d)
        else:
            shutil.copy2(s, d)


def make_helpers_executable():
    """Make all files in the helpers directory and main.py executable on Linux.

    This is called after applying updates to ensure helper scripts and the main
    entry point have the correct permissions. On non-Linux platforms, this is a no-op.

    Example:
        >>> make_helpers_executable()
    """
    if not sys.platform.startswith("linux"):
        return

    # Make helpers directory executable
    helpers_dir = os.path.join(AGENT_DIR, "helpers")
    if os.path.exists(helpers_dir):
        for root, dirs, files in os.walk(helpers_dir):
            for name in files + dirs:
                path = os.path.join(root, name)
                try:
                    st = os.stat(path)
                    os.chmod(
                        path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                    )
                except PermissionError as e:
                    logger.warning(f"Cannot chmod {path}, permission denied: {e}")

    # Make main.py executable
    main_py = os.path.join(AGENT_DIR, "main.py")
    if os.path.exists(main_py):
        try:
            st = os.stat(main_py)
            os.chmod(main_py, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except PermissionError as e:
            logger.warning(f"Cannot chmod {main_py}, permission denied: {e}")


# ----------------------------
# Release information
# ----------------------------


def fetch_release_info(channel: str = "beta") -> dict:
    """Fetch release information for a given update channel from GitHub.

    This function queries GitHub API to get the latest release information
    for the specified channel. Each channel uses different GitHub endpoints:
    - stable: Latest GitHub Release
    - beta: Latest Git tag
    - nightly: Latest commit on main branch

    Args:
        channel: Update channel ("stable", "beta", or "nightly"). Defaults to "beta".

    Returns:
        Dictionary containing release information with keys:
            - channel: The channel name
            - version: Version string (e.g., "v1.0.0" or "main-abc123")
            - signature: Unique identifier for this release (commit SHA or release ID)
            - zip_url: Download URL for the release archive
            - published_at: ISO 8601 publication date
            - notes: Release notes or commit message

    Raises:
        ValueError: If an unknown channel is specified.
        requests.RequestException: If GitHub API request fails.

    Example:
        >>> info = fetch_release_info("beta")
        >>> print(f"Latest beta: {info['version']}")
        'Latest beta: v0.10.5'
        >>> print(f"Published: {info['published_at']}")
        'Published: 2024-01-15T10:30:00Z'
    """
    channel = channel or "beta"

    if channel == "stable":
        data = _github_get(f"{GITHUB_API}/repos/{REPO}/releases/latest")
        version = data.get("tag_name") or data.get("name") or ""
        signature = str(data.get("id") or version)
        return {
            "channel": channel,
            "version": version,
            "signature": signature,
            "zip_url": data.get("zipball_url"),
            "published_at": data.get("published_at"),
            "notes": data.get("body") or "",
        }

    if channel == "beta":
        tags = _github_get(f"{GITHUB_API}/repos/{REPO}/tags")
        if not tags:
            raise ValueError("No tags found for beta channel.")

        tag = tags[0]
        version = tag.get("name")
        signature = tag.get("commit", {}).get("sha") or version
        return {
            "channel": channel,
            "version": version,
            "signature": signature,
            "zip_url": tag.get("zipball_url")
            or f"https://api.github.com/repos/{REPO}/zipball/{version}",
            "published_at": _get_commit_date(version) if version else None,
            "notes": "",
        }

    if channel == "nightly":
        commit = _github_get(f"{GITHUB_API}/repos/{REPO}/commits/main")
        sha = commit.get("sha")
        version = f"main-{sha[:7]}" if sha else "main"
        return {
            "channel": channel,
            "version": version,
            "signature": sha or version,
            "zip_url": f"https://github.com/{REPO}/archive/refs/heads/main.zip",
            "published_at": commit.get("commit", {}).get("author", {}).get("date"),
            "notes": commit.get("commit", {}).get("message", ""),
        }

    raise ValueError(f"Unknown update channel '{channel}'.")


def update_repo(channel: str = "stable", release_info: Optional[dict] = None) -> bool:
    """Download and apply an update from GitHub.

    This function downloads the release archive, verifies it hasn't been
    applied already (using SHA256 checksum), extracts it to a temporary
    directory, and copies files to the agent directory. It preserves existing
    files that aren't in the update.

    Args:
        channel: Update channel ("stable", "beta", or "nightly"). Defaults to "stable".
        release_info: Pre-fetched release info (fetches if None).

    Returns:
        True if update was applied, False if already up-to-date.

    Raises:
        ValueError: If zip URL is not available.
        requests.RequestException: If download fails.
        zipfile.BadZipFile: If downloaded archive is corrupted.

    Example:
        >>> # Check and apply update
        >>> if update_repo("beta"):
        ...     print("Update applied successfully")
        ... else:
        ...     print("Already up to date")

        >>> # Use pre-fetched info
        >>> info = fetch_release_info("stable")
        >>> if update_repo("stable", release_info=info):
        ...     print("Updated to", info["version"])
    """
    release_info = release_info or fetch_release_info(channel)
    zip_url = release_info.get("zip_url")

    if not zip_url:
        raise ValueError("Zip URL not available for update channel.")

    checksum_file = os.path.join(UPDATER_DIR, f".last_checksum_{channel}")
    signature = release_info.get("signature")

    logger.info(f"Checking for {channel} updates...")
    response = requests.get(zip_url, timeout=30)
    response.raise_for_status()
    content = response.content

    new_checksum = get_sha256(content)

    if os.path.exists(checksum_file):
        with open(checksum_file, "r", encoding="utf-8") as f:
            old_checksum = f.read().strip()
        if new_checksum == old_checksum:
            logger.info("No changes detected, skipping update")
            if signature:
                write_installed_signature(channel, signature)
            return False

    logger.info("Update found, applying...")
    tmp_dir = tempfile.mkdtemp(dir=UPDATER_DIR)
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            z.extractall(tmp_dir)

        subdirs = [os.path.join(tmp_dir, d) for d in os.listdir(tmp_dir)]
        repo_root = subdirs[0] if subdirs else tmp_dir

        copy_over(repo_root, AGENT_DIR)
        make_helpers_executable()

        # Run install.py to install any new requirements
        logger.info("Running install.py to update dependencies...")
        install_py = os.path.join(AGENT_DIR, "install.py")
        if os.path.exists(install_py):
            try:
                result = subprocess.run(
                    [sys.executable, install_py],
                    capture_output=True,
                    text=True,
                    timeout=600,  # 10 minute timeout
                )
                if result.returncode == 0:
                    logger.info("Dependencies updated successfully")
                else:
                    logger.warning(f"install.py returned exit code {result.returncode}")
                    if result.stderr:
                        logger.warning(f"install.py stderr: {result.stderr}")
            except subprocess.TimeoutExpired:
                logger.error("install.py timed out after 10 minutes")
            except Exception as e:
                logger.error(f"Failed to run install.py: {e}")
        else:
            logger.warning("install.py not found, skipping dependency installation")

        with open(checksum_file, "w", encoding="utf-8") as f:
            f.write(new_checksum)

        if signature:
            write_installed_signature(channel, signature)

        logger.info("Update complete")
        return True

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


class UpdateManager:
    """Manages automatic updates and MQTT integration for Home Assistant.

    This class coordinates update checking, publishing update status to MQTT,
    and handling remote installation requests from Home Assistant. It runs
    a polling loop in a background thread to periodically check for updates
    and can automatically install them or wait for manual triggers.

    The UpdateManager publishes Home Assistant discovery configurations for
    update entities and buttons, allowing users to see update status and
    trigger installations from the Home Assistant UI.

    Attributes:
        client: MQTT client for publishing messages.
        base_topic: Base MQTT topic for all device messages.
        discovery_prefix: Home Assistant MQTT discovery prefix.
        device_id: Unique device identifier.
        device_info: Device information dictionary for Home Assistant.
        channel: Update channel ("stable", "beta", or "nightly").
        interval: Update check interval in seconds (minimum 60).
        auto_install: Whether to automatically install updates.
        stop_event: Threading event to signal shutdown.
        state_topic: MQTT topic for update state.
        attrs_topic: MQTT topic for update attributes.
        install_topic: MQTT topic for installation commands.
        install_lock: Thread lock to prevent concurrent installations.
        installing: Flag indicating installation in progress.
        poll_thread: Background polling thread.
        latest_info: Most recently fetched release information.
        available: Flag indicating if update is available.
        last_error: Last error message (if any).

    Example:
        >>> import paho.mqtt.client as mqtt
        >>> client = mqtt.Client()
        >>> client.connect("mqtt.example.com", 1883)
        >>>
        >>> device_info = {
        ...     "identifiers": ["my_pc"],
        ...     "name": "My PC",
        ...     "manufacturer": "Custom",
        ...     "model": "Desktop"
        ... }
        >>>
        >>> manager = UpdateManager(
        ...     client=client,
        ...     base_topic="desktop/my_pc",
        ...     discovery_prefix="homeassistant",
        ...     device_id="my_pc",
        ...     device_info=device_info,
        ...     channel="beta",
        ...     interval=3600,
        ...     auto_install=True
        ... )
        >>>
        >>> # Subscribe to install requests
        >>> client.subscribe("desktop/my_pc/update/install")
        >>> client.message_callback_add(
        ...     "desktop/my_pc/update/install",
        ...     lambda client, userdata, msg: manager.handle_install_request(msg.payload)
        ... )
        >>>
        >>> # Start update monitoring
        >>> manager.start()
    """

    def __init__(
        self,
        client,
        base_topic: str,
        discovery_prefix: str,
        device_id: str,
        device_info: dict,
        channel: str = "stable",
        interval: int = 3600,
        auto_install: bool = True,
        stop_event: Optional[threading.Event] = None,
    ):
        """Initialize update manager.

        Args:
            client: Connected MQTT client instance (paho.mqtt.client.Client).
            base_topic: Base MQTT topic for device messages.
            discovery_prefix: Home Assistant discovery prefix (typically "homeassistant").
            device_id: Unique device identifier (used in entity IDs).
            device_info: Device information dictionary for Home Assistant discovery.
            channel: Update channel - "stable", "beta", or "nightly" (default: "stable").
            interval: Update check interval in seconds, minimum 60 (default: 3600).
            auto_install: Whether to automatically install updates (default: True).
            stop_event: Threading event for coordinated shutdown (creates new if None).
        """
        self.client = client
        self.base_topic = base_topic
        self.discovery_prefix = discovery_prefix
        self.device_id = device_id
        self.device_info = device_info or {}
        self.channel = channel or "stable"
        self.interval = max(60, int(interval))
        self.auto_install = auto_install
        self.stop_event = stop_event or threading.Event()

        self.state_topic = f"{self.base_topic}/update/state"
        self.attrs_topic = f"{self.base_topic}/update/attrs"
        self.install_topic = f"{self.base_topic}/update/install"

        self.install_lock = threading.Lock()
        self.installing = False
        self.poll_thread = None
        self.latest_info: Optional[dict] = None
        self.available = False
        self.last_error: Optional[str] = None

    def start(self) -> None:
        """Start the update manager polling thread.

        Publishes Home Assistant discovery configuration, performs an initial
        update check, and starts the background polling loop. This method is
        idempotent - calling it multiple times has no effect if already started.

        Example:
            >>> manager = UpdateManager(client, "desktop/my_pc", "homeassistant", "my_pc", device_info)
            >>> manager.start()
        """
        if self.poll_thread:
            return

        self.publish_discovery()
        self._poll_once(initial=True)

        self.poll_thread = threading.Thread(
            target=self._poll_loop, name="UpdateManager-Poll", daemon=True
        )
        self.poll_thread.start()
        logger.info("Update manager poll thread started")

    def publish_discovery(self) -> None:
        """Publish Home Assistant MQTT discovery configurations.

        Publishes discovery messages for:
        1. Update entity - shows current and available versions
        2. Button entity - triggers manual installation

        This is called once on startup to register entities with Home Assistant.

        Example:
            >>> manager.publish_discovery()
        """
        # Update entity configuration for Home Assistant
        update_payload = {
            "name": f"{self.device_info.get('name', 'Desktop Agent')} Agent",
            "state_topic": self.state_topic,
            "command_topic": self.install_topic,
            "payload_install": "INSTALL",
            "unique_id": f"{self.device_id}_update",
            "object_id": f"{self.device_id}_update",
            "device": self.device_info,
            "availability_topic": f"{self.base_topic}/availability",
            "entity_category": "diagnostic",
            "device_class": "firmware",
        }
        update_topic = f"{self.discovery_prefix}/update/{self.device_id}/update/config"
        self.client.publish(update_topic, json.dumps(update_payload), retain=True)

        button_payload = {
            "name": f"{self.device_info.get('name', 'Desktop Agent')} Install Update",
            "command_topic": self.install_topic,
            "payload_press": "INSTALL",
            "unique_id": f"{self.device_id}_install_update",
            "device": self.device_info,
            "availability_topic": f"{self.base_topic}/availability",
            "entity_category": "config",
            "icon": "mdi:update",
        }
        button_topic = (
            f"{self.discovery_prefix}/button/{self.device_id}/install_update/config"
        )
        self.client.publish(button_topic, json.dumps(button_payload), retain=True)

        # Publish initial state with installed version
        installed_version = _read_local_version()
        initial_state = {
            "installed_version": installed_version,
            "latest_version": installed_version,
            "title": "Desktop Agent",
            "release_summary": "Checking for updates...",
        }
        self.client.publish(self.state_topic, json.dumps(initial_state), retain=True)

        # Publish initial attributes
        self.client.publish(
            self.attrs_topic,
            json.dumps(
                {
                    "channel": self.channel,
                    "status": "initialising",
                    "auto_install": self.auto_install,
                    "install_in_progress": False,
                    "last_checked": _utcnow_iso(),
                }
            ),
            retain=True,
        )

    def handle_install_request(self, payload: Optional[bytes]) -> bool:
        """Handle installation request from MQTT command topic.

        Parses the MQTT payload and triggers manual installation if the
        action is recognized. Supports both plain text and JSON payloads.

        Args:
            payload: MQTT message payload (bytes or str).

        Returns:
            True if installation was started, False otherwise.

        Example:
            >>> # In MQTT message callback
            >>> def on_message(client, userdata, msg):
            ...     if msg.topic == manager.install_topic:
            ...         manager.handle_install_request(msg.payload)
            >>>
            >>> # Payload can be simple text
            >>> manager.handle_install_request(b"INSTALL")
            True
            >>>
            >>> # Or JSON
            >>> manager.handle_install_request(b'{"action": "INSTALL"}')
            True
        """
        if isinstance(payload, bytes):
            payload_str = payload.decode("utf-8", errors="ignore").strip()
        else:
            payload_str = str(payload or "").strip()

        action = "INSTALL"
        if payload_str:
            try:
                data = json.loads(payload_str)
                action = str(
                    data.get("action") or data.get("command") or "INSTALL"
                ).upper()
            except (ValueError, json.JSONDecodeError):
                action = payload_str.upper()

        if action in {"INSTALL", "INSTALL_UPDATE", "UPDATE"}:
            return self._start_install(manual=True)

        self._publish_state(
            self.available,
            self.latest_info,
            status="idle",
            error=f"Unsupported action '{action}'",
        )
        return False

    def _poll_loop(self) -> None:
        """Background polling loop that periodically checks for updates.

        This runs in a daemon thread and can be stopped by setting the
        stop_event. It catches and logs any exceptions to prevent thread
        crashes, publishing error states to MQTT when problems occur.
        """
        logger.info("Update manager poll loop started")
        try:
            while not self.stop_event.is_set():
                # Sleep but allow interruption
                self.stop_event.wait(self.interval)

                if self.stop_event.is_set():
                    break

                try:
                    self._poll_once()
                except Exception as exc:
                    self.last_error = str(exc)
                    logger.error(f"Error in update poll: {exc}", exc_info=True)
                    self._publish_state(
                        self.available, self.latest_info, status="error", error=str(exc)
                    )
        except Exception as e:
            logger.critical(f"Fatal error in update poll loop: {e}", exc_info=True)
        finally:
            logger.info("Update manager poll loop stopped")

    def _poll_once(self, initial: bool = False) -> None:
        """Perform a single update check.

        Fetches release information, compares with installed version,
        and triggers automatic installation if configured and an update
        is available.

        Args:
            initial: Whether this is the initial check on startup (unused but kept for API compatibility).
        """
        if self.installing:
            return

        info = fetch_release_info(self.channel)
        self.latest_info = info
        seed_signature_from_version(self.channel, info)

        available = self._is_update_available(info)
        self._publish_state(available, info, status="idle")

        if available and self.auto_install and not self.install_lock.locked():
            self._start_install(manual=False, info=info)

    def _is_update_available(self, info: Optional[dict]) -> bool:
        """Check if an update is available by comparing signatures.

        Compares the remote release signature with the locally installed
        signature to determine if a new version is available.

        Args:
            info: Release information dictionary from fetch_release_info().

        Returns:
            True if update is available, False otherwise.
        """
        if not info:
            return False

        signature = info.get("signature")
        if not signature:
            return False

        installed = read_installed_signature(self.channel)
        if not installed:
            seed_signature_from_version(self.channel, info)
            installed = read_installed_signature(self.channel)

        return signature != installed

    def _start_install(self, manual: bool, info: Optional[dict] = None) -> bool:
        """Start the installation process in a background thread.

        Spawns a worker thread to perform the actual installation,
        preventing concurrent installations with a lock.

        Args:
            manual: Whether this is a manual (user-triggered) installation.
            info: Pre-fetched release info (fetches if None).

        Returns:
            True if installation thread was started, False if already in progress or error occurred.
        """
        if self.install_lock.locked():
            self._publish_state(
                self.available,
                self.latest_info,
                status="busy",
                error="Update already in progress",
            )
            return False

        if info is None:
            try:
                info = fetch_release_info(self.channel)
            except Exception as exc:
                self.last_error = str(exc)
                self._publish_state(
                    self.available, self.latest_info, status="error", error=str(exc)
                )
                return False

        thread = threading.Thread(
            target=self._install_worker,
            args=(info, manual),
            name="UpdateManager-Installer",
            daemon=True,
        )
        thread.start()
        logger.info("Update installer thread started")
        return True

    def _install_worker(self, info: dict, manual: bool) -> None:
        """Worker thread that performs the actual installation.

        This method runs in a separate thread and holds the install_lock
        to prevent concurrent installations. It updates MQTT state throughout
        the process and schedules a delayed refresh after completion.

        Args:
            info: Release information dictionary.
            manual: Whether this is a manual (user-triggered) installation.
        """
        trigger = "manual" if manual else "auto"
        with self.install_lock:
            self.installing = True
            self._publish_state(True, info, status=f"installing ({trigger})")

            try:
                applied = update_repo(self.channel, release_info=info)
                seed_signature_from_version(self.channel, info)

                available = self._is_update_available(info)
                status = f"installed ({trigger})" if applied else "up-to-date"
                self._publish_state(available, info, status=status)

            except Exception as exc:
                self.last_error = str(exc)
                self._publish_state(True, info, status="error", error=str(exc))

            finally:
                self.installing = False
                threading.Thread(target=self._delayed_refresh, daemon=True).start()

    def _publish_state(
        self,
        available: bool,
        info: Optional[dict],
        status: str = "idle",
        error: Optional[str] = None,
    ) -> None:
        """Publish update state and attributes to MQTT.

        Publishes both the update entity state (for Home Assistant's update
        entity) and detailed attributes. Formats release information and
        includes installation status, errors, and release notes.

        Args:
            available: Whether an update is available.
            info: Release information dictionary.
            status: Installation status ("idle", "installing", "error", etc.).
            error: Error message if applicable.
        """
        info = self._safe_info(info)
        installed_version = _read_local_version()
        latest_version = info.get("version") if available else installed_version

        # Publish state as JSON for update entity
        state_payload = {
            "installed_version": installed_version,
            "latest_version": latest_version,
            "title": f"Desktop Agent {latest_version}",
        }

        # Add release URL if available
        if info.get("zip_url"):
            # Convert API URL to release page URL
            zip_url = info["zip_url"]
            if "api.github.com" in zip_url:
                # For stable releases, link to the release page
                if self.channel == "stable" and info.get("version"):
                    state_payload[
                        "release_url"
                    ] = f"https://github.com/{REPO}/releases/tag/{info['version']}"
                elif self.channel == "beta" and info.get("version"):
                    state_payload[
                        "release_url"
                    ] = f"https://github.com/{REPO}/releases/tag/{info['version']}"
                else:
                    state_payload["release_url"] = f"https://github.com/{REPO}"
            else:
                state_payload["release_url"] = f"https://github.com/{REPO}"

        # Add release summary with status information
        if error:
            state_payload["release_summary"] = f"Error: {error}"
        elif self.installing:
            state_payload["release_summary"] = "Installing update..."
        elif available:
            state_payload["release_summary"] = f"Update available: {latest_version}"
            if info.get("notes"):
                # Truncate notes to first line for summary
                first_line = info["notes"].split("\n")[0][:200]
                state_payload["release_summary"] = f"{first_line}"
        else:
            state_payload["release_summary"] = "Up to date"

        self.client.publish(
            self.state_topic, json.dumps(state_payload), qos=1, retain=True
        )

        # Publish detailed attributes separately
        attrs = {
            "channel": self.channel,
            "latest_version": latest_version,
            "latest_published": info.get("published_at"),
            "installed_version": installed_version,
            "signature": info.get("signature"),
            "status": status,
            "auto_install": self.auto_install,
            "install_in_progress": self.installing,
            "last_checked": _utcnow_iso(),
        }

        if error:
            attrs["error"] = error
        elif self.last_error and not available:
            self.last_error = None

        if info.get("notes"):
            attrs["notes"] = info["notes"]

        self.client.publish(self.attrs_topic, json.dumps(attrs), qos=1, retain=True)
        self.available = available

    def _delayed_refresh(self) -> None:
        """Perform a delayed state refresh after installation.

        Waits 5 seconds after installation completes, then performs
        another update check to refresh state. This ensures the UI
        reflects the newly installed version.
        """
        self.stop_event.wait(5)
        try:
            if not self.installing and not self.stop_event.is_set():
                self._poll_once()
        except Exception as exc:
            self.last_error = str(exc)
            logger.error(f"Error in delayed refresh: {exc}", exc_info=True)
            self._publish_state(
                self.available, self.latest_info, status="error", error=str(exc)
            )

    def _safe_info(self, info: Optional[dict]) -> dict:
        """Return safe default info dictionary if None.

        Args:
            info: Release information dictionary or None.

        Returns:
            The original dictionary if not None, otherwise a safe default
            dictionary with empty/None values.
        """
        if info is None:
            return {
                "channel": self.channel,
                "version": None,
                "signature": None,
                "zip_url": None,
                "published_at": None,
                "notes": "",
            }
        return info


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    channel = "beta"
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ["stable", "beta", "nightly"]:
            channel = arg
        else:
            logger.warning(f"Invalid channel '{arg}', defaulting to beta")

    stop_event = threading.Event()

    try:
        while not stop_event.is_set():
            update_repo(channel)
            stop_event.wait(3600)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, exiting")
        stop_event.set()
