#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HANDLER="$SCRIPT_DIR/powerd_handler.sh"

SOCKET="/tmp/powerd.sock"
rm -f "$SOCKET"

while true; do
    socat UNIX-LISTEN:"$SOCKET",fork EXEC:"$HANDLER"
    sleep 1
done
