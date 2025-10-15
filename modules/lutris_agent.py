from modules.config import IGDB_CLIENT, IGDB_TOKEN
from modules.igdb import IGDBClient
import json

igdb = IGDBClient(IGDB_CLIENT, IGDB_TOKEN)

game_info = igdb.search_game("My Summer Car")

if game_info:
    # Sanitized response
    print(f"Found {game_info['name']}")
    print(game_info['summary'])
    print(game_info['release_date'])
    print(game_info['genres'])
    print(game_info['developers'])
    # Raw response
    #print(json.dumps(game_info, indent=2))
