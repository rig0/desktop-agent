#!/usr/bin/env bash

# -----------------------------------------------------
# Wait until network is up (NetworkManager managed)
# -----------------------------------------------------
if command -v nm-online >/dev/null 2>&1; then
    echo "Waiting for network..."
    nm-online -q --timeout=300
fi

# -----------------------------------------------------
# Path setup
# -----------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"
AGENT_DIR="$PARENT_DIR"
CONFIG_FILE="$AGENT_DIR/config/config.ini"

TOOLBOX_NAME="desktop-agent"

# -----------------------------------------------------
# INI parser (section + key)
# -----------------------------------------------------
get_config() {
    local section="$1" key="$2"
    awk -F' *= *' -v section="[$section]" -v key="$key" '
        $0 == section { in_section=1; next }
        /^\[/ { in_section=0 }
        in_section && $1 == key { print $2; exit }
    ' "$CONFIG_FILE"
}

# -----------------------------------------------------
# Script selection
# -----------------------------------------------------
SCRIPTS=(
    "$AGENT_DIR/desktop_agent.py"
    "$AGENT_DIR/media_agent_linux.py"
)

RUN_UPDATER="$(get_config helpers auto_updates | tr '[:upper:]' '[:lower:]')"

if [[ "$RUN_UPDATER" == "true" ]]; then
    SCRIPTS+=("$AGENT_DIR/updater.py")
fi

# -----------------------------------------------------
# Environment setup
# -----------------------------------------------------
export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export PULSE_SERVER="${PULSE_SERVER:-unix:${XDG_RUNTIME_DIR}/pulse/native}"

# -----------------------------------------------------
# Run scripts inside toolbox
# -----------------------------------------------------
for SCRIPT in "${SCRIPTS[@]}"; do
    echo "Starting: $SCRIPT"
    toolbox run -c "$TOOLBOX_NAME" python3 "$SCRIPT" &
done

wait
