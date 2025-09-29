#!/usr/bin/env bash

read cmd

case "$cmd" in
    reboot)
        echo "Executing host reboot..."
        sudo systemctl reboot
        ;;
    poweroff|shutdown)
        echo "Executing host shutdown..."
        sudo systemctl poweroff
        ;;
    *)
        echo "Unknown command: $cmd"
        ;;
esac
