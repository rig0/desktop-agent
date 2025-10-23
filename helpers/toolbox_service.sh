#!/usr/bin/env bash

# Wait until network is up (NetworkManager managed)
if command -v nm-online >/dev/null 2>&1; then
    echo "Waiting for network..."
    nm-online -q --timeout=300
fi

# Path setup
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"
AGENT_DIR="$PARENT_DIR"

TOOLBOX_NAME="desktop-agent"

# Script
SCRIPT="$AGENT_DIR/main.py"

# Environment setup
#export DISPLAY="${DISPLAY:-:0}"
#export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
#export PULSE_SERVER="${PULSE_SERVER:-unix:${XDG_RUNTIME_DIR}/pulse/native}"

# Run script inside toolbox
# -----------------------------------------------------
#toolbox run -c "$TOOLBOX_NAME" python3 "$SCRIPT" &
toolbox run --container "$TOOLBOX_NAME" --privileged \
  --volume /dev:/dev \
  --volume /sys:/sys \
  --volume /run/udev:/run/udev \
  python3 "$SCRIPT" &
wait
