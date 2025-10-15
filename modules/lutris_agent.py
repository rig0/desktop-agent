# Attempt relative import for use as a module within a package structure
try:
    from .config import IGDB_CLIENT, IGDB_TOKEN
    from .igdb import IGDBClient
# Fall back to direct import which assumes the script is being ran standalone
except ImportError:
    from config import IGDB_CLIENT, IGDB_TOKEN
    from igdb import IGDBClient
import json

def fetch_game_info(game):
    igdb = IGDBClient(IGDB_CLIENT, IGDB_TOKEN)
    game_info = igdb.search_game(game)
    if game_info:
        # Sanitized response
        print(f"Found {game_info['name']}")
        print(game_info['summary'])
        print(game_info['release_date'])
        print(game_info['genres'])
        print(game_info['developers'])
        # Raw response
        #print(json.dumps(game_info, indent=2))

if __name__ == "__main__":
    game = "My Summer Car"
    fetch_game_info(game)
