#!/usr/bin/env bash

# -----------------------------------------------------
# Wait until network is up (NetworkManager managed)
# -----------------------------------------------------
if command -v nm-online >/dev/null 2>&1; then
    echo "Waiting for network..."
    nm-online -q --timeout=300
fi

# Get the directory of the current script.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
MAIN="$SCRIPT_DIR/../main.py"

python3 $MAIN