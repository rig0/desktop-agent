#!/usr/bin/env bash

# -----------------------------------------------------
# Wait until network is up (NetworkManager managed)
# -----------------------------------------------------
if command -v nm-online >/dev/null 2>&1; then
    echo "Waiting for network..."
    nm-online -q --timeout=300
fi

python3 /var/home/rambo/Apps/Agent/main.py