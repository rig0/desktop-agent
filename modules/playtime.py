import sqlite3
import os
import json

# -------------------------------------
# Lutris Playtime Parser
# -------------------------------------

def get_lutris_game_playtime(db_path, game_name):
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT playtime FROM games WHERE LOWER(name) = LOWER(?)",
            (game_name,)
        )
        result = cursor.fetchone()
        conn.close()

        if result:
            return float(result[0])
        else:
            return None

    except sqlite3.Error as e:
        raise RuntimeError(f"SQLite error: {e}")


def get_lutris_game_service(db_path, game_name):
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT service FROM games WHERE LOWER(name) = LOWER(?)",
            (game_name,)
        )
        result = cursor.fetchone()
        conn.close()

        if result:
            return result[0]
        else:
            return None

    except sqlite3.Error as e:
        raise RuntimeError(f"SQLite error: {e}")


def get_lutris_service_game_playtime(db_path, game_name, service=None):
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if service:
            cursor.execute(
                "SELECT details FROM service_games WHERE LOWER(name) = LOWER(?) AND LOWER(service) = LOWER(?)",
                (game_name, service)
            )
        else:
            cursor.execute(
                "SELECT details FROM service_games WHERE LOWER(name) = LOWER(?)",
                (game_name,)
            )

        result = cursor.fetchone()
        conn.close()

        if not result:
            return None

        # Parse the JSON string
        try:
            details = json.loads(result[0])
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON for game '{game_name}'")

        # Extract playtime (in hours)
        playtime = details.get("playtime_forever")
        if playtime is None:
            return None

        return float(playtime / 60)

    except sqlite3.Error as e:
        raise RuntimeError(f"SQLite error: {e}")


def get_playtime(db, game_name):
    playtime = get_lutris_game_playtime(db, game)
    service = get_lutris_game_service(db, game)

    print(f"Lutris playtime: {playtime} Hours")
    print(f"Game Service: {service}")

    if playtime == 0 and service == 'steam':
        playtime = get_lutris_service_game_playtime(db, game, 'steam')
        print(f"Steam playtime: {playtime} Hours")

    return playtime


if __name__ == "__main__":
    db = "./pga.db"
    game = "My Summer Car"
    playtime = get_playtime(db, game)

    if playtime is not None:
        print(f"Playtime for '{game}': {playtime:.2f} hours")
    else:
        print(f"Game '{game}' not found in the database.")

