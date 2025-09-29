#!/usr/bin/env bash

SOCKET="/tmp/powerd.sock"
rm -f "$SOCKET"

while true; do
    socat UNIX-LISTEN:"$SOCKET",fork EXEC:/var/home/rambo/Apps/Agent/helpers/powerd_handler.sh
    sleep 1
done
