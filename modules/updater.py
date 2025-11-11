import hashlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone
from typing import Optional

import requests

from modules.config import REPO_OWNER, REPO_NAME, VERSION_PATH

# Config
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
    headers = {"Accept": "application/vnd.github+json"}
    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.json()


def _get_commit_date(ref: str) -> Optional[str]:
    try:
        data = _github_get(f"{GITHUB_API}/repos/{REPO}/commits/{ref}")
        return data.get("commit", {}).get("author", {}).get("date")
    except requests.RequestException:
        return None


def _normalize_version(version: Optional[str]) -> str:
    if not version:
        return ""
    return version.strip().lower().lstrip("v")


def _read_local_version() -> str:
    try:
        with open(VERSION_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _signature_path(channel: str) -> str:
    safe_channel = channel or "stable"
    return os.path.join(UPDATER_DIR, f".last_signature_{safe_channel}")


def read_installed_signature(channel: str) -> Optional[str]:
    path = _signature_path(channel)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def write_installed_signature(channel: str, signature: Optional[str]) -> None:
    if not signature:
        return
    path = _signature_path(channel)
    with open(path, "w", encoding="utf-8") as f:
        f.write(signature)


def seed_signature_from_version(channel: str, release_info: Optional[dict]) -> None:
    if not release_info or read_installed_signature(channel):
        return

    remote_version = release_info.get("version")
    local_version = _read_local_version()
    if remote_version and _normalize_version(remote_version) == _normalize_version(local_version):
        write_installed_signature(channel, release_info.get("signature"))


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ----------------------------
# File helpers
# ----------------------------

def get_sha256(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()

# Overwrite new files without touching other files
def copy_over(src, dst):
    os.makedirs(dst, exist_ok=True)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)

        if os.path.isdir(s):
            copy_over(s, d)
        else:
            shutil.copy2(s, d)

# Make Linux scripts executable
def make_helpers_executable():
    helpers_dir = os.path.join(AGENT_DIR, "helpers")
    if not os.path.exists(helpers_dir):
        return

    if sys.platform.startswith("linux"):
        for root, dirs, files in os.walk(helpers_dir):
            for name in files + dirs:
                path = os.path.join(root, name)
                try:
                    st = os.stat(path)
                    os.chmod(path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                except PermissionError:
                    print(f"[Updater] Warning: Cannot chmod {path}, permission denied")


# ----------------------------
# Release information
# ----------------------------

def fetch_release_info(channel: str = "beta") -> dict:
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
            "zip_url": tag.get("zipball_url") or f"https://api.github.com/repos/{REPO}/zipball/{version}",
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
    release_info = release_info or fetch_release_info(channel)
    zip_url = release_info.get("zip_url")

    if not zip_url:
        raise ValueError("Zip URL not available for update channel.")

    checksum_file = os.path.join(UPDATER_DIR, f".last_checksum_{channel}")
    signature = release_info.get("signature")

    print(f"[Updater] Checking for {channel} updates...")
    response = requests.get(zip_url, timeout=30)
    response.raise_for_status()
    content = response.content

    new_checksum = get_sha256(content)

    if os.path.exists(checksum_file):
        with open(checksum_file, "r", encoding="utf-8") as f:
            old_checksum = f.read().strip()
        if new_checksum == old_checksum:
            print("[Updater] No changes detected, skipping update.")
            if signature:
                write_installed_signature(channel, signature)
            return False

    print("[Updater] Update found, applying...")
    tmp_dir = tempfile.mkdtemp(dir=UPDATER_DIR)
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            z.extractall(tmp_dir)

        subdirs = [os.path.join(tmp_dir, d) for d in os.listdir(tmp_dir)]
        repo_root = subdirs[0] if subdirs else tmp_dir

        copy_over(repo_root, AGENT_DIR)
        make_helpers_executable()

        with open(checksum_file, "w", encoding="utf-8") as f:
            f.write(new_checksum)

        if signature:
            write_installed_signature(channel, signature)

        print("[Updater] Update complete.")
        return True

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


class UpdateManager:
    #Publishes update status via MQTT and handles install requests.
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
    ):
        self.client = client
        self.base_topic = base_topic
        self.discovery_prefix = discovery_prefix
        self.device_id = device_id
        self.device_info = device_info or {}
        self.channel = channel or "stable"
        self.interval = max(60, int(interval))
        self.auto_install = auto_install

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
        if self.poll_thread:
            return

        self.publish_discovery()
        self._poll_once(initial=True)

        self.poll_thread = threading.Thread(target=self._poll_loop, name="UpdateMonitor", daemon=True)
        self.poll_thread.start()

    def publish_discovery(self) -> None:
        # Update entity configuration for Home Assistant
        update_payload = {
            "name": f"{self.device_info.get('name', 'Desktop Agent')} Update",
            "state_topic": self.state_topic,
            "command_topic": self.install_topic,
            "payload_install": "INSTALL",
            "unique_id": f"{self.device_id}_update",
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
        button_topic = f"{self.discovery_prefix}/button/{self.device_id}/install_update/config"
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
        if isinstance(payload, bytes):
            payload_str = payload.decode("utf-8", errors="ignore").strip()
        else:
            payload_str = str(payload or "").strip()

        action = "INSTALL"
        if payload_str:
            try:
                data = json.loads(payload_str)
                action = str(data.get("action") or data.get("command") or "INSTALL").upper()
            except (ValueError, json.JSONDecodeError):
                action = payload_str.upper()

        if action in {"INSTALL", "INSTALL_UPDATE", "UPDATE"}:
            return self._start_install(manual=True)

        self._publish_state(self.available, self.latest_info, status="idle", error=f"Unsupported action '{action}'")
        return False

    def _poll_loop(self) -> None:
        while True:
            time.sleep(self.interval)
            try:
                self._poll_once()
            except Exception as exc:
                self.last_error = str(exc)
                self._publish_state(self.available, self.latest_info, status="error", error=str(exc))

    def _poll_once(self, initial: bool = False) -> None:
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
        if self.install_lock.locked():
            self._publish_state(self.available, self.latest_info, status="busy", error="Update already in progress")
            return False

        if info is None:
            try:
                info = fetch_release_info(self.channel)
            except Exception as exc:
                self.last_error = str(exc)
                self._publish_state(self.available, self.latest_info, status="error", error=str(exc))
                return False

        thread = threading.Thread(
            target=self._install_worker,
            args=(info, manual),
            name="UpdateInstaller",
            daemon=True,
        )
        thread.start()
        return True

    def _install_worker(self, info: dict, manual: bool) -> None:
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

    def _publish_state(self, available: bool, info: Optional[dict], status: str = "idle", error: Optional[str] = None) -> None:
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
                    state_payload["release_url"] = f"https://github.com/{REPO}/releases/tag/{info['version']}"
                elif self.channel == "beta" and info.get("version"):
                    state_payload["release_url"] = f"https://github.com/{REPO}/releases/tag/{info['version']}"
                else:
                    state_payload["release_url"] = f"https://github.com/{REPO}"
            else:
                state_payload["release_url"] = f"https://github.com/{REPO}"

        # Add release summary with status information
        if error:
            state_payload["release_summary"] = f"Error: {error}"
        elif self.installing:
            state_payload["release_summary"] = f"Installing update..."
        elif available:
            state_payload["release_summary"] = f"Update available: {latest_version}"
            if info.get("notes"):
                # Truncate notes to first line for summary
                first_line = info["notes"].split("\n")[0][:200]
                state_payload["release_summary"] = f"{first_line}"
        else:
            state_payload["release_summary"] = "Up to date"

        self.client.publish(self.state_topic, json.dumps(state_payload), qos=1, retain=True)

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
        time.sleep(5)
        try:
            if not self.installing:
                self._poll_once()
        except Exception as exc:
            self.last_error = str(exc)
            self._publish_state(self.available, self.latest_info, status="error", error=str(exc))

    def _safe_info(self, info: Optional[dict]) -> dict:
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
    channel = "stable"
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ["stable", "beta", "nightly"]:
            channel = arg
        else:
            print(f"Invalid channel '{arg}', defaulting to stable.")

    try:
        while True:
            update_repo(channel)
            time.sleep(3600)
    except KeyboardInterrupt:
        print("[Updater] Exiting.")
