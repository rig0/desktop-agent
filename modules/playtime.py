import sqlite3
import os
import json

# -------------------------------------
# Lutris Playtime Parser
# -------------------------------------

def find_lutris_db():
    possible_paths = [
        os.path.expanduser("~/.local/share/lutris/pga.db"),
        os.path.expanduser("~/.var/app/net.lutris.Lutris/data/lutris/pga.db"),  # Flatpak path
    ]

    for path in possible_paths:
        if os.path.isfile(path):
            return path
    return None  

def get_lutris_playtime(game_name):
    db_path = find_lutris_db()
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Try the 'games' table
        cursor.execute(
            "SELECT playtime, service FROM games WHERE LOWER(name) = LOWER(?)",
            (game_name,)
        )
        row = cursor.fetchone()

        if row:
            playtime, service = row
            playtime = round(float(playtime),2)
        else:
            playtime, service = None, None

        # If playtime is 0 and game is a steam game use the service_games table
        if (playtime is None or playtime == 0) and service and service.lower() == 'steam':
            cursor.execute(
                "SELECT details FROM service_games WHERE LOWER(name) = LOWER(?) AND LOWER(service) = LOWER(?)",
                (game_name, service)
            )
            row = cursor.fetchone()
            if row:
                try:
                    details = json.loads(row[0])
                    playtime = round(float(details.get("playtime_forever", 0) / 60), 2)
                except json.JSONDecodeError:
                    playtime = 0

        conn.close()
        return playtime

    except sqlite3.Error as e:
        raise RuntimeError(f"SQLite error: {e}")

# Standalone testing
if __name__ == "__main__":
    game = "My Summer Car"
    playtime = get_lutris_playtime(game)

    if playtime is not None:
        print(f"Playtime for '{game}': {playtime} hours")
    else:
        print(f"Game '{game}' not found in the database.")


