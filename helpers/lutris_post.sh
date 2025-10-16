#!/bin/bash

# Get the directory of the current script.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Define GAME_NAME_FILE path assuming it lives in the parent directory of the script.
GAME_NAME_FILE="$SCRIPT_DIR/../data/current_game.txt"

# Clear the GAME_NAME from the file to indicate the game has stopped.
> "$GAME_NAME_FILE"
