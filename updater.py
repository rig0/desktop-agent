import os
import shutil
import tempfile
import requests
import zipfile
import io
import time
import hashlib

REPO_ZIP = "https://rigslab.com/Rambo/hass-desktop-agent/archive/main.zip"
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKSUM_FILE = os.path.join(AGENT_DIR, ".last_checksum")

def get_sha256(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()

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

    # Copy files into AGENT_DIR (overwriting existing ones)
    for item in os.listdir(repo_root):
        src = os.path.join(repo_root, item)
        dst = os.path.join(AGENT_DIR, item)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    # Save new checksum
    with open(CHECKSUM_FILE, "w") as f:
        f.write(new_checksum)

    # Cleanup tmp dir
    shutil.rmtree(tmp_dir)

if __name__ == "__main__":
    while True:
        update_repo()
        time.sleep(300)  # 5 min while testing
