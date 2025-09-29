#!/usr/bin/env bash

# Wait until network is up (NetworkManager managed)
if command -v nm-online >/dev/null 2>&1; then
    echo "Waiting for network..."
    nm-online -q --timeout=300
fi

# ----------------------------
# Configuration
# ----------------------------
TOOLBOX_NAME="desktop-agent"
SCRIPTS=(
    "/home/rambo/Apps/Agent/desktop_agent.py"
    "/home/rambo/Apps/Agent/media_agent_linux.py"
)

# ----------------------------
# Environment setup
# ----------------------------
# X11 support
export DISPLAY="${DISPLAY:-:0}"
# Wayland (if using)
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
# PulseAudio audio
export PULSE_SERVER="${PULSE_SERVER:-unix:${XDG_RUNTIME_DIR}/pulse/native}"

# ----------------------------
# Run scripts inside toolbox
# ----------------------------
for SCRIPT in "${SCRIPTS[@]}"; do
    # Run each script in background
    toolbox run -c "$TOOLBOX_NAME" python3 "$SCRIPT" &
done