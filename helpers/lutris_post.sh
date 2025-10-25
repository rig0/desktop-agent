#!/bin/bash

# Get the directory of the current script.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Define GAME_NAME_FILE path relative to this script
GAME_NAME_FILE="$SCRIPT_DIR/../data/game_agent/current_game"

# Clear the GAME_NAME from the file to indicate the game has stopped.
> "$GAME_NAME_FILE"
