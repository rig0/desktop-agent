import os
import shutil
import tempfile
import requests
import zipfile
import io
import time
import hashlib
import sys
import stat

# personal repo link
# REPO_ZIP = "https://rigslab.com/Rambo/hass-desktop-agent/archive/main.zip"
# github link
REPO_ZIP = "https://github.com/rig0/hass-desktop-agent/archive/refs/heads/main.zip"
AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKSUM_FILE = os.path.join(AGENT_DIR, ".last_checksum")


def get_sha256(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def copy_over(src, dst):
    # Copy files/dirs from src into dst without overwriting user config files.
    os.makedirs(dst, exist_ok=True)

    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)

        if os.path.isdir(s):
            copy_over(s, d)
        else:
            shutil.copy2(s, d)

def make_helpers_executable():
    helpers_dir = os.path.join(AGENT_DIR, "helpers")
    if not os.path.exists(helpers_dir):
        return

    if sys.platform.startswith("linux"):
        for root, dirs, files in os.walk(helpers_dir):
            for name in files:
                file_path = os.path.join(root, name)
                try:
                    st = os.stat(file_path)
                    os.chmod(file_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                except PermissionError:
                    print(f"Warning: Cannot chmod {file_path}, permission denied")
            for name in dirs:
                dir_path = os.path.join(root, name)
                try:
                    st = os.stat(dir_path)
                    os.chmod(dir_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                except PermissionError:
                    print(f"Warning: Cannot chmod {dir_path}, permission denied")


def update_repo():
    # Download zip archive
    r = requests.get(REPO_ZIP)
    r.raise_for_status()
    content = r.content

    # Calculate checksum
    new_checksum = get_sha256(content)

    # Check against last run
    if os.path.exists(CHECKSUM_FILE):
        with open(CHECKSUM_FILE, "r") as f:
            old_checksum = f.read().strip()
        if new_checksum == old_checksum:
            print("No changes detected, skipping update.")
            return

    print("Update found, applying...")

    # Create temp dir
    tmp_dir = tempfile.mkdtemp(dir=AGENT_DIR)

    # Extract zip into temp dir
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        z.extractall(tmp_dir)

    # Repo root folder (hass-desktop-agent-main)
    subdirs = [os.path.join(tmp_dir, d) for d in os.listdir(tmp_dir)]
    repo_root = subdirs[0] if subdirs else tmp_dir

    # Copy everything into AGENT_DIR (including config/),
    # overwriting only files that exist in the repo
    copy_over(repo_root, AGENT_DIR)

    # Make /helpers executable if on Linux
    make_helpers_executable()

    # Save new checksum
    with open(CHECKSUM_FILE, "w") as f:
        f.write(new_checksum)

    # Cleanup tmp dir
    shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    while True:
        update_repo()
        time.sleep(3600)  # every hour
