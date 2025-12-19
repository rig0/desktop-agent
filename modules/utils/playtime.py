"""Game playtime tracking from Lutris and Steam.

This module provides utilities for extracting game playtime information
from Lutris and Steam databases on Linux systems. It searches multiple
possible database locations including native and Flatpak installations.

The playtime data is sourced from:
- Lutris native database (~/.local/share/lutris/pga.db)
- Lutris Flatpak database (~/.var/app/net.lutris.Lutris/data/lutris/pga.db)
- Steam playtime via Lutris's service_games table (for games launched through Lutris)

Example:
    >>> from modules.utils.playtime import get_lutris_playtime
    >>> playtime = get_lutris_playtime("Elden Ring")
    >>> if playtime:
    ...     print(f"Played {playtime} hours")
    ... else:
    ...     print("Game not found or no playtime recorded")
"""

# Standard library imports
import json
import logging
import os
import sqlite3

logger = logging.getLogger(__name__)


def find_lutris_db():
    """Locate the Lutris database file.

    Searches common installation paths for the Lutris PGA (Pretty Good Archive)
    database, checking both native and Flatpak installations.

    Returns:
        Absolute path to the database file if found, None otherwise.

    Example:
        >>> db_path = find_lutris_db()
        >>> if db_path:
        ...     print(f"Found Lutris database at: {db_path}")
        ... else:
        ...     print("Lutris database not found")
    """
    possible_paths = [
        os.path.expanduser("~/.local/share/lutris/pga.db"),
        os.path.expanduser(
            "~/.var/app/net.lutris.Lutris/data/lutris/pga.db"
        ),  # Flatpak path
    ]

    for path in possible_paths:
        if os.path.isfile(path):
            return path
    return None


def get_lutris_playtime(game_name):
    """Get playtime in hours for a game from Lutris database.

    Searches the Lutris database for the specified game and returns
    playtime in hours. For Steam games with no Lutris playtime recorded,
    it falls back to Steam's playtime data from the service_games table.

    The function performs case-insensitive game name matching.

    Args:
        game_name: Name of the game to look up (case-insensitive).

    Returns:
        Playtime in hours (float, rounded to 2 decimals), or None if:
        - Lutris database not found
        - Game not found in database
        - Database query fails

    Example:
        >>> # Get playtime for a game
        >>> playtime = get_lutris_playtime("Elden Ring")
        >>> if playtime:
        ...     print(f"Elden Ring: {playtime} hours")
        'Elden Ring: 127.45 hours'

        >>> # Game not found
        >>> playtime = get_lutris_playtime("Nonexistent Game")
        >>> print(playtime)
        None

        >>> # For Steam games, automatically falls back to Steam data
        >>> playtime = get_lutris_playtime("Counter-Strike 2")
        >>> print(f"{playtime} hours")
        '523.67 hours'
    """
    db_path = find_lutris_db()
    if db_path is None:
        logger.info("Lutris database not found")
        return None

    if not os.path.isfile(db_path):
        logger.info(f"Database file does not exist: {db_path}")
        return None

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Try the 'games' table
        cursor.execute(
            "SELECT playtime, service FROM games WHERE LOWER(name) = LOWER(?)",
            (game_name,),
        )
        row = cursor.fetchone()

        if row:
            playtime, service = row
            playtime = round(float(playtime), 2)
        else:
            playtime, service = None, None

        # If playtime is 0 and game is a steam game use the service_games table
        if (playtime is None or playtime == 0) and service and service.lower() == "steam":
            cursor.execute(
                "SELECT details FROM service_games WHERE LOWER(name) = LOWER(?) AND LOWER(service) = LOWER(?)",
                (game_name, service),
            )
            row = cursor.fetchone()
            if row:
                try:
                    details = json.loads(row[0])
                    # Handle case where playtime_forever exists but is None
                    playtime_forever = details.get("playtime_forever") or 0
                    playtime = round(float(playtime_forever / 60), 2)
                except json.JSONDecodeError:
                    playtime = 0

        conn.close()
        return playtime

    except sqlite3.Error as e:
        logger.error(f"SQLite error: {e}")
        return None


# Standalone testing
if __name__ == "__main__":
    game = "My Summer Car"
    playtime = get_lutris_playtime(game)

    if playtime is not None:
        print(f"Playtime for '{game}': {playtime} hours")
    else:
        print(f"Game '{game}' not found in the database.")
