import os, shutil, tempfile, requests, zipfile, io, time, hashlib, sys, stat

# Config
REPO = "rig0/hass-desktop-agent"
AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPDATER_DIR = os.path.join(AGENT_DIR, "data", "updater")

# Create updater data folder is it doesn't exist
os.makedirs(UPDATER_DIR, exist_ok=True)

# Get sha256 checksum
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

# Make linux scripts executable
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


# Fetch URLs depending on channel
def get_repo_zip(channel="stable"):
    if channel == "stable":
        api_url = f"https://api.github.com/repos/{REPO}/releases/latest"
        r = requests.get(api_url, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("zipball_url")

    if channel == "beta":
        api_url = f"https://api.github.com/repos/{REPO}/tags"
        r = requests.get(api_url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not data:
            raise ValueError("No tags found for beta channel.")
        return data[0].get("zipball_url")

    if channel == "nightly":
        return f"https://github.com/{REPO}/archive/refs/heads/main.zip"

    # fallback only once
    print(f"[Updater] Unknown channel '{channel}', defaulting to stable.")
    return get_repo_zip("stable")


def update_repo(channel="stable"):
    zip_url = get_repo_zip(channel)
    checksum_file = os.path.join(UPDATER_DIR, f".last_checksum_{channel}")

    print(f"[Updater] Checking for {channel} updates...")

    r = requests.get(zip_url, timeout=30)
    r.raise_for_status()
    content = r.content

    new_checksum = get_sha256(content)

    if os.path.exists(checksum_file):
        with open(checksum_file, "r") as f:
            old_checksum = f.read().strip()
        if new_checksum == old_checksum:
            print("[Updater] No changes detected, skipping update.")
            return

    print("[Updater] Update found, applying...")

    tmp_dir = tempfile.mkdtemp(dir=UPDATER_DIR)

    with zipfile.ZipFile(io.BytesIO(content)) as z:
        z.extractall(tmp_dir)

    subdirs = [os.path.join(tmp_dir, d) for d in os.listdir(tmp_dir)]
    repo_root = subdirs[0] if subdirs else tmp_dir

    copy_over(repo_root, AGENT_DIR)
    make_helpers_executable()

    with open(checksum_file, "w") as f:
        f.write(new_checksum)

    shutil.rmtree(tmp_dir)
    print("[Updater] Update complete.")


if __name__ == "__main__":
    channel = "stable"  # default
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ["stable", "beta", "nightly"]:
            channel = arg
        else:
            print(f"Invalid channel '{arg}', defaulting to stable.")

    while True:
        update_repo(channel)
        time.sleep(3600)  # check every hour
