#!/bin/bash

# Get the directory of the current script.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Define GAME_NAME_FILE path assuming it lives in the parent directory of the script.
GAME_NAME_FILE="$SCRIPT_DIR/../data/game_agent/current_game"

# Write the GAME_NAME to the designated file.
echo "$GAME_NAME" > "$GAME_NAME_FILE"

# Fetch the env from lutris
#env > "$SCRIPT_DIR/../data/game_agent/lutris_prelaunch_env.txt"

# Log the launch event with additional information (optional).
#echo "Launching $GAME_NAME ($LUTRIS_GAME_UUID) [$STORE]" >> "$SCRIPT_DIR/../data/game_agent/lutris_launch.log"
