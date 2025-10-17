#!/usr/bin/env bash
set -e

# ----------------------------
# Install system dependencies
# ----------------------------

# Base packages
if [ "$DISTRO" = "debian" ]; then
    BASE_PKGS="
        python3
        python3-pip
        python3-venv
        python3-dev
        build-essential
        pkg-config
        libffi-dev
        libssl-dev
        zlib1g-dev
        libxml2-dev
        libxslt1-dev
        libpq-dev
        curl
    "
elif [ "$DISTRO" = "fedora" ]; then
    BASE_PKGS="
        python3
        python3-pip
        python3-virtualenv
        python3-devel
        gcc
        gcc-c++
        make
        pkg-config
        libffi-devel
        openssl-devel
        zlib-devel
        libxml2-devel
        libxslt-devel
        libpq-devel
        curl
    "
fi

# Optional GPU packages
GPU_PKGS=()
$INSTALL_AMD && GPU_PKGS+=("radeontop")
$INSTALL_INTEL && GPU_PKGS+=("intel-gpu-tools")

# Convert BASE_PKGS multi-line string to array
read -r -a BASE_ARR <<< "$BASE_PKGS"

# Combine base and GPU packages
ALL_PKGS=("${BASE_ARR[@]}" "${GPU_PKGS[@]}")

# Install dependencies
if [ "$DISTRO" = "debian" ]; then
    sudo apt update
    sudo apt install -y "${ALL_PKGS[@]}"
elif [ "$DISTRO" = "fedora" ]; then
    if [ "$IMMUTABLE" = true ]; then
        echo "⚠️ Immutable Fedora detected. You can layer packages with rpm-ostree or use toolbox."
        echo "It's recommended to layer the packages. Running in a toolbox requires some workarounds."
        read -p "Do you want to layer packages into the system? (Y/n): " choice
        if [[ "$choice" =~ ^[Nn]$ ]]; then
            echo "Skipping layering. Use toolbox for installation instead."
            echo "Example:"
            echo "  toolbox create desktop-agent"
            echo "  toolbox enter desktop-agent"
            echo "  sudo dnf install -y ${ALL_PKGS[*]}"
        else
            sudo rpm-ostree install "${ALL_PKGS[@]}"
            echo "Reboot required to apply changes."
        fi
    else
        sudo dnf install -y "${ALL_PKGS[@]}"
    fi
fi

echo "✅ All dependencies installed."


# ----------------------------
# Create configuration file
# ----------------------------

echo "=== Desktop Agent Config Setup ==="

CONFIG_DIR="../data"
CONFIG_FILE="$CONFIG_DIR/config.ini"

mkdir -p "$CONFIG_DIR"

# Device section
DEFAULT_DEVICE_NAME=$(hostname)
read -p "Device name [$DEFAULT_DEVICE_NAME]: " DEVICE_NAME
DEVICE_NAME="$(echo -n "${DEVICE_NAME:-$DEFAULT_DEVICE_NAME}" | xargs)"

read -p "Update interval in seconds [15]: " UPDATE_INTERVAL
UPDATE_INTERVAL="$(echo -n "${UPDATE_INTERVAL:-15}" | xargs)"

# MQTT section (mandatory)
echo "Enter MQTT settings (mandatory, installer will fail if empty)"
while true; do
    read -p "MQTT broker IP/hostname: " MQTT_BROKER
    MQTT_BROKER="$(echo -n "$MQTT_BROKER" | xargs)"
    [ -n "$MQTT_BROKER" ] && break
    echo "MQTT broker cannot be empty!"
done

while true; do
    read -p "MQTT port [1883]: " MQTT_PORT
    MQTT_PORT="$(echo -n "${MQTT_PORT:-1883}" | xargs)"
    [ "$MQTT_PORT" -gt 0 ] 2>/dev/null && break
    echo "MQTT port must be a positive number"
done

while true; do
    read -p "MQTT username: " MQTT_USER
    MQTT_USER="$(echo -n "$MQTT_USER" | xargs)"
    [ -n "$MQTT_USER" ] && break
    echo "MQTT username cannot be empty!"
done

while true; do
    read -p "MQTT password: " MQTT_PASS
    MQTT_PASS="$(echo -n "$MQTT_PASS" | xargs)"
    [ -n "$MQTT_PASS" ] && break
    echo "MQTT password cannot be empty!"
done

# Modules section (optional)
read -p "Enable API module? [y/N]: " API_CHOICE
API_CHOICE="$(echo -n "${API_CHOICE:-N}" | xargs)"
if [[ "$API_CHOICE" =~ ^[Yy]$ ]]; then
    API_ENABLED=true
    read -p "Override API port? [default 5555]: " API_PORT
    API_PORT="$(echo -n "${API_PORT:-5555}" | xargs)"
else
    API_ENABLED=false
    API_PORT=5555
fi

read -p "Enable updates module? [y/N]: " UPDATES_CHOICE
UPDATES_CHOICE="$(echo -n "${UPDATES_CHOICE:-N}" | xargs)"
if [[ "$UPDATES_CHOICE" =~ ^[Yy]$ ]]; then
    UPDATES_ENABLED=true
    read -p "Update interval in hours [default 1h]: " UPDATES_HOURS
    UPDATES_HOURS="$(echo -n "${UPDATES_HOURS:-1}" | xargs)"
    UPDATES_INTERVAL=$((UPDATES_HOURS * 3600))
else
    UPDATES_ENABLED=false
    UPDATES_INTERVAL=3600
fi

read -p "Enable media agent module? [y/N]: " MEDIA_CHOICE
MEDIA_CHOICE="$(echo -n "${MEDIA_CHOICE:-N}" | xargs)"
MEDIA_ENABLED=false
[[ "$MEDIA_CHOICE" =~ ^[Yy]$ ]] && MEDIA_ENABLED=true

read -p "Enable game agent module? [y/N]: " GAME_CHOICE
GAME_CHOICE="$(echo -n "${GAME_CHOICE:-N}" | xargs)"
if [[ "$GAME_CHOICE" =~ ^[Yy]$ ]]; then
    GAME_ENABLED=true
    echo
    echo "To use the IGDB API, you need a client ID and access token."
    echo "Read more: https://api-docs.igdb.com/#authentication"
    echo "Reminder: access token, not client secret!"
    read -p "IGDB Client ID: " IGDB_CLIENT_ID
    IGDB_CLIENT_ID="$(echo -n "$IGDB_CLIENT_ID" | xargs)"
    read -p "IGDB Access Token: " IGDB_TOKEN
    IGDB_TOKEN="$(echo -n "$IGDB_TOKEN" | xargs)"
else
    GAME_ENABLED=false
    IGDB_CLIENT_ID=None
    IGDB_TOKEN=None
fi

# Write config.ini
cat > "$CONFIG_FILE" <<EOL
[device]
name = $DEVICE_NAME
interval = $UPDATE_INTERVAL

[mqtt]
broker = $MQTT_BROKER
port = $MQTT_PORT
username = $MQTT_USER
password = $MQTT_PASS

[modules]
api = $API_ENABLED
updates = $UPDATES_ENABLED
media_agent = $MEDIA_ENABLED
game_agent = $GAME_ENABLED

[api]
port = $API_PORT

[updates]
interval = $UPDATES_INTERVAL

[igdb]
client_id = $IGDB_CLIENT_ID
token = $IGDB_TOKEN
EOL

echo "✅ Config file written to $CONFIG_FILE"


# ----------------------------
# Install python dependencies
# ----------------------------

echo "=== Desktop Agent python dependency installer ==="

# Change to parent directory
SCRIPT_DIR=$(dirname "$0")
cd "$SCRIPT_DIR/.." || exit 1

# Install Python dependencies
echo "Installing Python dependencies from requirements-linux.txt..."

# Check if python is installed
command -v python3 >/dev/null 2>&1 || { echo "Python3 is not installed! Aborting."; exit 1; }

# Check if requirements file exists
[ -f requirements-linux.txt ] || { echo "requirements-linux.txt not found!"; exit 1; }

# Install
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements-linux.txt

# Check if nvidia driver is installed
if command -v nvidia-smi >/dev/null 2>&1; then
    python3 -m pip install GPUtil
else
    echo "❌ nvidia-smi not found (NVIDIA driver missing or not loaded). Skipping GPUtil"
fi

echo "✅ Python dependencies installed."