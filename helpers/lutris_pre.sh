#!/bin/bash

# Get the directory of the current script.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Define GAME_NAME_FILE path assuming it lives in the parent directory of the script.
GAME_NAME_FILE="$SCRIPT_DIR/../data/current_game.txt"

# Write the GAME_NAME to the designated file.
echo "$GAME_NAME" > "$GAME_NAME_FILE"

# Log the launch event with additional information (optional).
#echo "Launching $GAME_NAME ($LUTRIS_GAME_UUID) [$STORE]" >> "$SCRIPT_DIR/../data/lutris_launch.log"
